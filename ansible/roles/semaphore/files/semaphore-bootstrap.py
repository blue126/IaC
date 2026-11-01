#!/usr/bin/env python3
"""Create the employee-lifecycle project and wsctl templates in Semaphore.

Idempotent: objects are matched by name and created only when missing.
Prints one JSON line: {"changed": bool, "project_id": int}.
"""
import http.cookiejar,json,sys,urllib.request
from pathlib import Path

BASE='http://127.0.0.1:3000/api'
PROJECT='employee-lifecycle'
# A filesystem path is used in place by Semaphore, so tasks run the deployed
# work tree that git push keeps current.
REPOSITORY={'name':'employee-admin','git_url':'/srv/remotecc/employee-admin','git_branch':'main'}
SCRIPT='semaphore/wsctl.sh'
# name -> (arguments, survey variables, allow overriding arguments per task)
TEMPLATES={
    'wsctl status':(['status'],[],False),
    'wsctl deliver':(['deliver'],[{'name':'WSCTL_APPROVE','title':'approval_sha256 (empty = plan only)','required':False,'type':''}],True),
}
SCHEDULES={'wsctl status':'*/30 * * * *'}

jar=http.cookiejar.CookieJar()
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def call(method,path,body=None):
    data=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(BASE+path,data=data,method=method,headers={'Content-Type':'application/json'})
    with opener.open(req) as resp:
        raw=resp.read()
    return json.loads(raw) if raw else None

def ensure(path,name,body):
    for item in call('GET',path) or []:
        if item.get('name')==name:return item['id'],False
    return call('POST',path,body)['id'],True

def main():
    password=Path(sys.argv[1]).read_text().strip()
    call('POST','/auth/login',{'auth':sys.argv[2],'password':password})
    changed=False
    project,c=ensure('/projects',PROJECT,{'name':PROJECT});changed|=c
    p=f'/project/{project}'
    key,c=ensure(p+'/keys','none',{'name':'none','type':'none','project_id':project});changed|=c
    repo,c=ensure(p+'/repositories',REPOSITORY['name'],{**REPOSITORY,'project_id':project,'ssh_key_id':key});changed|=c
    current=call('GET',p+f'/repositories/{repo}')
    if current.get('git_url')!=REPOSITORY['git_url']:
        call('PUT',p+f'/repositories/{repo}',{**current,**REPOSITORY});changed=True
    env,c=ensure(p+'/environment','default',{'name':'default','project_id':project,'json':'{}','env':'{}'});changed|=c
    inv,c=ensure(p+'/inventory','none',{'name':'none','project_id':project,'type':'static','inventory':'','ssh_key_id':key});changed|=c
    for name,(arguments,survey,override) in TEMPLATES.items():
        tid,c=ensure(p+'/templates',name,{'name':name,'project_id':project,'app':'bash','playbook':SCRIPT,
            'repository_id':repo,'environment_id':env,'inventory_id':inv,'arguments':json.dumps(arguments),
            'allow_override_args_in_task':override,'survey_vars':survey,'type':''})
        changed|=c
        if name in SCHEDULES:
            _,c=ensure(p+'/schedules',name,{'name':name,'project_id':project,'template_id':tid,'cron_format':SCHEDULES[name],'active':True});changed|=c
    print(json.dumps({'changed':changed,'project_id':project}))

if __name__=='__main__':main()
