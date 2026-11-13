"""Operator CLI. Run from the repository root with the local environment active."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
from access_intake.ingest import load_document,SourceDocument,InputExportError
from access_intake.processing import error_record
from access_intake.providers.mock import MockProvider
from access_intake.store import Store,encoded,public_settings
from access_intake.worker import run_pending

ROOT=Path(__file__).resolve().parents[1]
def emit(value):print(json.dumps(value,indent=2,ensure_ascii=False))
def provider_factory():
    cache={}
    def factory(settings):
        key=encoded(settings)
        if key not in cache:
            if settings.get('provider','mock')=='mock':cache[key]=MockProvider(settings.get('mock_manifest',ROOT/'tests/mock_responses/s04-manifest.json'))
            elif settings['provider']=='openai':
                from access_intake.providers.openai import OpenAIProvider
                cache[key]=OpenAIProvider(settings)
            else:raise ValueError('unsupported provider configuration')
        return cache[key]
    return factory

def parser():
    main=argparse.ArgumentParser(description='Prepare access requests for human review')
    commands=main.add_subparsers(dest='command',required=True)
    for name in ('intake','resume','queue','show','history','retry','refresh'):
        command=commands.add_parser(name);command.add_argument('--db',default='var/intake.sqlite')
        if name in ('intake','resume','retry','refresh'):
            command.add_argument('--workers',type=int,default=None);command.add_argument('--rpm',type=float,default=None)
        if name in ('intake','refresh'):
            command.add_argument('--config');command.add_argument('--provider',choices=['mock','openai']);command.add_argument('--mock-manifest');command.add_argument('--policy')
        if name=='intake':command.add_argument('inputs',nargs='+')
        if name in ('show','history'):command.add_argument('document_id')
        if name=='queue':
            command.add_argument('--watch',action='store_true');command.add_argument('--interval',type=float,default=1);command.add_argument('--iterations',type=int)
        if name=='retry':
            command.add_argument('--attempt-id',type=int,required=True);command.add_argument('--document-id',required=True);command.add_argument('--force',action='store_true')
        if name=='refresh':command.add_argument('--force',action='store_true');command.add_argument('--document-id')
    return main

def configuration(args):
    settings=json.loads(Path(args.config).read_text()) if args.config else {}
    if not isinstance(settings,dict):raise ValueError('configuration must be a JSON object')
    if args.provider:settings['provider']=args.provider
    settings.setdefault('provider','mock')
    settings.setdefault('model','fixture-v1' if settings['provider']=='mock' else 'gpt-5.4-mini-2026-03-17')
    if args.mock_manifest:settings['mock_manifest']=str(Path(args.mock_manifest).resolve())
    if settings['provider']=='mock':settings.setdefault('mock_manifest',str(ROOT/'tests/mock_responses/s04-manifest.json'))
    for field in ('mock_manifest','schema_path','prompt_path','policy_path'):
        if field in settings:settings[field]=str(Path(settings[field]).resolve())
    policy={}
    if args.policy:
        settings['policy_path']=str(Path(args.policy).resolve())
        if Path(args.policy).suffix=='.json':policy=json.loads(Path(args.policy).read_text())
    if not isinstance(policy,dict) or set(policy)-{'staging_read_requires_security'}:raise ValueError('unsupported policy options')
    if 'staging_read_requires_security' in policy and not isinstance(policy['staging_read_requires_security'],bool):raise ValueError('policy risk option must be boolean')
    public_settings(settings)
    return settings,policy

def run(args):
    store=Store(args.db)
    if args.command=='queue':
        count=0
        while True:
            emit(store.queue());count+=1
            if not args.watch or args.iterations and count>=args.iterations:return 0
            time.sleep(max(.05,args.interval))
    if args.command in ('show','history'):
        values=store.history(args.document_id) if args.command=='history' else [r for r in store.queue() if r['document_id']==args.document_id]
        if not values:raise ValueError('document not found')
        emit(values if args.command=='history' else values[0]);return 0
    errors=[];settings={}
    if args.command=='intake':
        settings,policy=configuration(args)
        paths=[]
        for value in args.inputs:
            path=Path(value);paths.extend(sorted(path.glob('*.json')) if path.is_dir() else [path])
        duplicates={name for name,count in Counter(p.name for p in paths).items() if count>1}
        for name in sorted(duplicates):errors.append(name+': duplicate input filename; separate colliding feeds')
        for path in paths:
            if path.name in duplicates:continue
            try:document=load_document(path)
            except InputExportError as error:
                errors.append(str(error))
                try:raw=path.read_bytes()
                except OSError:continue
                document=SourceDocument(path.name,raw,hashlib.sha256(raw).hexdigest(),'',{})
                revision=store.register(document,settings,policy=policy)
                source='mock' if settings['provider']=='mock' else settings['provider']+'/'+settings['model']
                store.record_result(revision,error_record(document,source,str(error)));continue
            store.register(document,settings,policy=policy)
    elif args.command=='retry':
        history=store.history(args.document_id)
        if not any(row['attempt_id']==args.attempt_id for row in history):raise ValueError('attempt does not belong to the requested document')
        store.retry(args.attempt_id,force=args.force)
    elif args.command=='refresh':
        settings,policy=configuration(args)
        store.refresh(settings if args.config or args.provider or args.mock_manifest else None,policy=policy if args.policy else None,document_id=args.document_id,force=args.force)
    workers=args.workers or settings.get('workers',4)
    rpm=args.rpm if args.rpm is not None else settings.get('rpm',0 if settings.get('provider','mock')=='mock' else 30)
    run_pending(store,provider_factory(),workers=workers,rpm=rpm)
    queue=store.queue()
    for error in errors:print(error,file=sys.stderr)
    emit({'documents':len(queue),'errors':len(errors),'pending':len(store.pending())})
    return 1 if errors or any(row.get('error') for row in queue) else 0

def main():
    args=parser().parse_args()
    try:return run(args)
    except KeyboardInterrupt:
        print('Interrupted; completed results are saved. Use resume for unfinished work.',file=sys.stderr);return 130
    except (ValueError,OSError) as error:
        # Configuration and input errors have controlled, actionable messages.
        print('Operation failed; check paths, configuration and recorded state.',file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
