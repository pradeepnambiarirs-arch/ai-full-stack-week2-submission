"""SQLite current pointers, immutable revisions and append-only attempt outcomes."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import shlex
import os
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
def encoded(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value): return hashlib.sha256(value).hexdigest()
def public_settings(value):
    if isinstance(value,dict):
        if any(str(k).lower() in {'api_key','authorization','password','secret','credential','access_token'} for k in value):
            raise ValueError('credentials must be supplied through the provider credential loader, not persisted settings')
        for v in value.values(): public_settings(v)
    elif isinstance(value,list):
        for v in value: public_settings(v)
    return value

class Store:
    def __init__(self,path,*,clock=time.time):
        self.path=str(Path(path).resolve()); self.clock=clock
        Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection(begin=False) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY,document_id TEXT NOT NULL,source BLOB NOT NULL,source_sha256 TEXT NOT NULL,configuration TEXT NOT NULL,policy TEXT NOT NULL,fingerprint TEXT NOT NULL,prompt_sha256 TEXT NOT NULL,schema_sha256 TEXT NOT NULL,policy_version TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(document_id TEXT PRIMARY KEY,desired INTEGER NOT NULL REFERENCES revisions(id),current_attempt INTEGER);
            CREATE TABLE IF NOT EXISTS jobs(revision INTEGER PRIMARY KEY REFERENCES revisions(id),state TEXT NOT NULL DEFAULT 'queued',token INTEGER NOT NULL DEFAULT 0,worker TEXT,lease_until REAL);
            CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,revision INTEGER NOT NULL REFERENCES revisions(id),token INTEGER,result TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,document_id TEXT NOT NULL,revision INTEGER NOT NULL,action TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS limits(name TEXT PRIMARY KEY,value REAL NOT NULL);
            ''')
        with self.connection(True) as db:
            columns={row['name'] for row in db.execute('PRAGMA table_info(revisions)')}
            for column in ('schema_text','prompt_text','policy_text'):
                if column not in columns:db.execute(f"ALTER TABLE revisions ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    @contextmanager
    def connection(self,write=False,begin=True):
        db=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON'); db.execute('PRAGMA busy_timeout=5000'); db.execute('PRAGMA synchronous=FULL')
        try:
            if begin: db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except BaseException:
            db.rollback(); raise
        finally: db.close()
    def _event(self,db,doc,revision,action):
        db.execute('INSERT INTO events(document_id,revision,action,created) VALUES(?,?,?,?)',(doc,revision,action,self.clock()))
    def register(self,document,configuration,*,policy=None,force=False,expected_revision=None):
        public_settings(configuration); policy=public_settings(policy or {})
        prompt=Path(configuration.get('prompt_path',ROOT/'access_intake/prompts/extract.txt')).read_bytes()
        schema=Path(configuration.get('schema_path',ROOT/'snapshot.schema.json')).read_bytes()
        policy_bytes=Path(configuration.get('policy_path',ROOT/'materials/office-policy.md')).read_bytes()
        policy_version=digest(policy_bytes+encoded(policy).encode())
        relevant={k:v for k,v in configuration.items() if k not in {'workers','rpm','timeout','lease_seconds','busy_timeout'}}
        assets={k:digest(Path(configuration[k]).read_bytes()) for k in ('mock_manifest',) if configuration.get(k)}
        fingerprint=digest(encoded([document.source_sha256,relevant,assets,digest(prompt),digest(schema),policy_version]).encode())
        with self.connection(True) as db:
            old=db.execute('SELECT r.id,r.fingerprint FROM documents d JOIN revisions r ON r.id=d.desired WHERE d.document_id=?',(document.document_id,)).fetchone()
            if expected_revision is not None and (old is None or old['id']!=expected_revision):raise ValueError('stale source revision; refresh the desired source instead')
            if old and old['fingerprint']==fingerprint and not force: return old['id']
            revision=db.execute('INSERT INTO revisions(document_id,source,source_sha256,configuration,policy,fingerprint,prompt_sha256,schema_sha256,policy_version,created) VALUES(?,?,?,?,?,?,?,?,?,?)',(document.document_id,document.source_bytes,document.source_sha256,encoded(configuration),encoded(policy),fingerprint,digest(prompt),digest(schema),policy_version,self.clock())).lastrowid
            db.execute('UPDATE revisions SET schema_text=?,prompt_text=?,policy_text=? WHERE id=?',(schema.decode('utf-8'),prompt.decode('utf-8'),policy_bytes.decode('utf-8'),revision))
            if old: db.execute("UPDATE jobs SET state='superseded' WHERE revision=? AND state='queued'",(old['id'],))
            db.execute('INSERT INTO documents(document_id,desired) VALUES(?,?) ON CONFLICT(document_id) DO UPDATE SET desired=excluded.desired',(document.document_id,revision))
            db.execute('INSERT INTO jobs(revision) VALUES(?)',(revision,))
            self._event(db,document.document_id,revision,'registered')
            return revision
    def record_result(self,revision,result,*,token=None,before_commit=None):
        with self.connection(True) as db:
            row=db.execute('SELECT r.*,j.token,j.state,d.desired FROM revisions r JOIN jobs j ON j.revision=r.id JOIN documents d ON d.document_id=r.document_id WHERE r.id=?',(revision,)).fetchone()
            if row is None: raise ValueError('unknown source revision')
            if result['document_id']!=row['document_id'] or result['source_sha256']!=row['source_sha256']:
                raise ValueError('result and source revision disagree')
            if token is not None and (token!=row['token'] or row['state']!='running'): return None
            attempt=db.execute('INSERT INTO attempts(revision,token,result,created) VALUES(?,?,?,?)',(revision,token,encoded(result),self.clock())).lastrowid
            if result.get('error'):
                result=dict(result,retry_command=shlex.join(['python3','-m','access_intake','retry','--db',self.path,'--document-id',row['document_id'],'--attempt-id',str(attempt)]))
                db.execute('UPDATE attempts SET result=? WHERE id=?',(encoded(result),attempt))
            if before_commit: before_commit()
            if row['desired']==revision:
                db.execute('UPDATE documents SET current_attempt=? WHERE document_id=?',(attempt,row['document_id']))
            db.execute("UPDATE jobs SET state='finished',worker=NULL,lease_until=NULL WHERE revision=?",(revision,))
            self._event(db,row['document_id'],revision,'published' if row['desired']==revision else 'superseded-result')
            return attempt
    def _record(self,row):
        result=json.loads(row['result'])
        result.update(attempt_id=row['attempt_id'],revision_id=row['id'],configuration=json.loads(row['configuration']),policy_version=row['policy_version'],prompt_sha256=row['prompt_sha256'],schema_sha256=row['schema_sha256'])
        return result
    def queue(self):
        with self.connection() as db:
            rows=db.execute('SELECT d.document_id,d.desired,d.current_attempt,j.state,r.source_sha256 FROM documents d JOIN revisions r ON r.id=d.desired JOIN jobs j ON j.revision=r.id ORDER BY d.document_id').fetchall()
            output=[]
            for row in rows:
                if row['current_attempt']:
                    value=db.execute('SELECT r.*,a.id AS attempt_id,a.result FROM attempts a JOIN revisions r ON r.id=a.revision WHERE a.id=?',(row['current_attempt'],)).fetchone()
                    result=self._record(value)
                    result.update(pending=row['state'] in ('queued','running'),desired_source_sha256=row['source_sha256'],previous_version=value['id']!=row['desired'])
                else:
                    result=dict(document_id=row['document_id'],source_sha256=row['source_sha256'],status='pending',owner=None,next_action='resume-processing',extraction=None,error=None,pending=True,previous_version=False)
                output.append(result)
            return output
    def history(self,document_id):
        with self.connection() as db:
            return [self._record(row) for row in db.execute('SELECT r.*,a.id AS attempt_id,a.result FROM attempts a JOIN revisions r ON r.id=a.revision WHERE r.document_id=? ORDER BY a.id',(document_id,))]
    def revision(self,revision):
        with self.connection() as db:
            row=db.execute('SELECT * FROM revisions WHERE id=?',(revision,)).fetchone()
            if row is None:raise ValueError('unknown source revision')
            value=dict(row);value['configuration']=json.loads(value['configuration']);value['policy']=json.loads(value['policy']);return value
    def pending(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT j.* FROM jobs j JOIN documents d ON d.desired=j.revision WHERE j.state IN ('queued','running')")]
    def claim(self,worker,*,lease_seconds=120,max_inflight=4,rpm=0):
        if lease_seconds<=0 or max_inflight<1 or rpm<0:raise ValueError('invalid worker limits')
        now=self.clock()
        with self.connection(True) as db:
            if db.execute("SELECT count(*) FROM jobs WHERE state='running'").fetchone()[0]>=max_inflight:return None
            candidates=db.execute("SELECT r.*,j.token FROM jobs j JOIN revisions r ON r.id=j.revision JOIN documents d ON d.desired=r.id WHERE j.state='queued' ORDER BY r.id")
            for row in candidates:
                settings=json.loads(row['configuration']);provider=settings.get('provider','mock')
                names=('next_start:'+provider,'cooldown:'+provider)
                blocked=max([r[0] for r in db.execute('SELECT value FROM limits WHERE name IN (?,?)',names)]+[0])
                if blocked>now:continue
                token=row['token']+1
                db.execute("UPDATE jobs SET state='running',worker=?,token=?,lease_until=? WHERE revision=?",(worker,token,now+lease_seconds,row['id']))
                effective_rpm=rpm or settings.get('rpm',30 if provider!='mock' else 0)
                if effective_rpm:db.execute('INSERT INTO limits(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',(names[0],now+60/effective_rpm))
                self._event(db,row['document_id'],row['id'],'claimed')
                value=dict(row);value.update(token=token,configuration=settings,policy=json.loads(row['policy']));return value
            return None
    def renew(self,revision,token,lease_seconds=120):
        with self.connection(True) as db:
            return db.execute("UPDATE jobs SET lease_until=? WHERE revision=? AND token=? AND state='running'",(self.clock()+lease_seconds,revision,token)).rowcount==1
    def cooldown(self,provider,seconds):
        with self.connection(True) as db:
            db.execute('INSERT INTO limits(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=max(value,excluded.value)',('cooldown:'+provider,self.clock()+max(0,seconds)))
    def recover(self):
        with self.connection(True) as db:
            rows=db.execute("SELECT r.*,j.token,d.desired FROM jobs j JOIN revisions r ON r.id=j.revision JOIN documents d ON d.document_id=r.document_id WHERE j.state='running' AND j.lease_until<=?",(self.clock(),)).fetchall()
            for row in rows:
                settings=json.loads(row['configuration']);provider=settings.get('provider','mock')
                result=dict(document_id=row['document_id'],source_sha256=row['source_sha256'],response_source='mock' if provider=='mock' else provider+'/'+settings.get('model','unknown'),extraction=None,status='error',owner='IT Service Desk',next_action='retry-extraction',error='interrupted worker lease expired; resume or retry extraction')
                attempt=db.execute('INSERT INTO attempts(revision,token,result,created) VALUES(?,?,?,?)',(row['id'],row['token'],encoded(result),self.clock())).lastrowid
                desired=row['id']==row['desired']
                if desired:db.execute('UPDATE documents SET current_attempt=? WHERE document_id=?',(attempt,row['document_id']))
                db.execute('UPDATE jobs SET state=?,token=token+1,worker=NULL,lease_until=NULL WHERE revision=?',('queued' if desired else 'superseded',row['id']))
                self._event(db,row['document_id'],row['id'],'interrupted')
            return len(rows)
    def retry(self,attempt_id,*,force=False):
        with self.connection() as db:
            row=db.execute('SELECT r.*,a.result,j.state,d.desired FROM attempts a JOIN revisions r ON r.id=a.revision JOIN documents d ON d.document_id=r.document_id JOIN jobs j ON j.revision=r.id WHERE a.id=?',(attempt_id,)).fetchone()
            if row is None:raise ValueError('unknown attempt')
            if row['id']!=row['desired']:raise ValueError('stale attempt; refresh the desired source instead')
            if row['state'] in ('queued','running'):raise ValueError('processing is already pending')
            if json.loads(row['result'])['error'] is None and not force:raise ValueError('successful attempt requires --force')
            revision=dict(row)
        from access_intake.worker import document_from_revision
        return self.register(document_from_revision(revision),json.loads(revision['configuration']),policy=json.loads(revision['policy']),force=True,expected_revision=revision['id'])
    def refresh(self,configuration=None,*,policy=None,document_id=None,force=False):
        with self.connection() as db:
            query='SELECT r.* FROM documents d JOIN revisions r ON r.id=d.desired'
            rows=db.execute(query+(' WHERE d.document_id=?' if document_id else ''),(document_id,) if document_id else ()).fetchall()
        from access_intake.worker import document_from_revision
        return [self.register(document_from_revision(row),configuration if configuration is not None else json.loads(row['configuration']),policy=policy if policy is not None else json.loads(row['policy']),force=force,expected_revision=row['id']) for row in rows]
    def schema_snapshot(self,job):
        if not job.get('schema_text'):return job['configuration'].get('schema_path',str(ROOT/'snapshot.schema.json'))
        folder=Path(self.path).parent/'assets';folder.mkdir(exist_ok=True)
        path=folder/(job['schema_sha256']+'.json')
        if path.exists():
            if path.read_text(encoding='utf-8')!=job['schema_text']:raise ValueError('stored schema snapshot is corrupted')
            return str(path)
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=folder,delete=False) as stream:
            temporary=stream.name;stream.write(job['schema_text']);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        return str(path)
