"""Configurable OpenAI Responses integration with injectable offline transport."""
import json
import os
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from access_intake.providers.base import ProviderError
from access_intake.processing import load_extraction_prompt
from access_intake.validation import DEFAULT_SCHEMA_PATH

DEFAULT_MODEL='gpt-5.4-mini-2026-03-17'
def credential_from_environment():
    value=os.environ.get('API_KEY')
    if not value:raise ProviderError('authentication')
    return value

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def http_transport(request,*,timeout):
    with build_opener(NoRedirect()).open(request,timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))

class OpenAIProvider:
    def __init__(self,configuration,*,transport=None,credential_supplier=None):
        self.configuration=dict(configuration);self.transport=transport or http_transport
        self.credential_supplier=credential_supplier or credential_from_environment
        self._mock=transport is not None;self.retry_after=0;self.reported_model=None
        self.response_source='mock' if self._mock else 'openai/'+configuration.get('model',DEFAULT_MODEL)
        self.request_evidence=None
    def extract(self,message,*,source_sha256,configuration):
        settings=dict(self.configuration,**configuration)
        endpoint=settings.get('endpoint','https://api.openai.com/v1/responses')
        url=urlsplit(endpoint)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ProviderError('configuration')
        schema=json.loads(settings['_schema_text']) if settings.get('_schema_text') else json.loads(Path(settings.get('schema_path',DEFAULT_SCHEMA_PATH)).read_text())
        instructions=settings.get('_prompt_text') or load_extraction_prompt()
        if settings.get('prompt_path') and not settings.get('_prompt_text'):instructions=Path(settings['prompt_path']).read_text()
        body=dict(model=settings.get('model',DEFAULT_MODEL),instructions=instructions,input=[{'role':'user','content':[{'type':'input_text','text':message}]}],text={'format':{'type':'json_schema','name':'access_snapshot','strict':True,'schema':schema}},store=False,max_output_tokens=settings.get('max_output_tokens',4096),reasoning={'effort':settings.get('reasoning_effort','none')})
        if 'temperature' in settings:body['temperature']=settings['temperature']
        self.request_evidence={'observation':'mock-transport' if self._mock else 'provider-request','request':{'method':'POST','endpoint':endpoint,'headers':{'Authorization':'[REDACTED]','Content-Type':'application/json'},'body':body},'response_handling':['HTTP errors are sanitized without hidden retries','Require completed envelope and output message','Reject refusal, missing/multiple text payloads and malformed JSON','Validate supplied schema, date format and exact source quotes before routing']}
        credential=self.credential_supplier()
        if not isinstance(credential,str) or not credential:raise ProviderError('authentication')
        request=Request(endpoint,data=json.dumps(body).encode('utf-8'),headers={'Authorization':'Bearer '+credential,'Content-Type':'application/json'},method='POST')
        self.retry_after=0
        try:raw=self.transport(request,timeout=settings.get('timeout',60))
        except HTTPError as error:
            if error.code==429:
                try:self.retry_after=min(300,max(0,float(error.headers.get('Retry-After','30'))))
                except (TypeError,ValueError):self.retry_after=30
            raise ProviderError('rate-limit' if error.code==429 else 'authentication' if error.code in (401,403) else 'unavailable') from None
        except (TimeoutError,URLError,OSError):raise ProviderError('unavailable') from None
        except (ValueError,TypeError):raise ProviderError('malformed-response') from None
        if not isinstance(raw,dict) or not isinstance(raw.get('output'),list):raise ProviderError('malformed-response')
        model=raw.get('model',settings.get('model',DEFAULT_MODEL))
        if not isinstance(model,str) or credential in model:model=settings.get('model',DEFAULT_MODEL)
        self.reported_model=model
        self.response_source='mock' if self._mock else 'openai/'+model
        messages=[item for item in raw['output'] if isinstance(item,dict) and item.get('type')=='message']
        content=[part for item in messages for part in item.get('content',[]) if isinstance(part,dict)]
        refused=any(part.get('type')=='refusal' for part in content)
        texts=[part.get('text') for part in content if part.get('type')=='output_text']
        if not refused and len(texts)!=1:raise ProviderError('malformed-response')
        return {'status':raw.get('status'),'message_status':'completed' if messages and all(item.get('status')=='completed' for item in messages) else 'incomplete','refusal':refused,'output_text':texts[0] if len(texts)==1 else ''}
