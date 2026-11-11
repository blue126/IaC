#!/usr/bin/env python3
"""Create the remotecc project and wsctl templates in Semaphore.

Idempotent: objects are matched by name and created only when missing; a
template whose description or form changed is updated in place.
Prints one JSON line: {"changed": bool, "project_id": int}.
"""
import http.cookiejar,json,sys,urllib.request
from pathlib import Path

BASE='http://127.0.0.1:3000/api'
PROJECT='remotecc'
# A filesystem path is used in place by Semaphore, so tasks run the deployed
# work tree that git push keeps current.
REPOSITORY={'name':'wsctl','git_url':'/srv/remotecc/wsctl','git_branch':'main'}
SCRIPT='semaphore/wsctl.sh'
def field(name,title,description):
    return {'name':name,'title':title,'description':description,'required':False,'type':''}
APPROVE=field('WSCTL_APPROVE','批准码','留空只出计划，不改任何东西。把计划输出里的 approval_sha256 填到这里再运行一次才会执行。')
DEVICE=field('WSCTL_DEVICE','设备 ID','开户结果里的 device_id。')
# name -> (arguments, survey variables, allow overriding arguments per task, description)
TEMPLATES={
    'wsctl status':(['status'],[],False,'只读。查看所有工作区的实时状态。每 30 分钟自动运行。'),
    'wsctl request':(['request'],[],False,'把网站上的新申请拉到执行器。输出里的 pulled 是申请编号，开户时填。'),
    'wsctl provision':(['provision'],[
        field('WSCTL_APPLICATION','申请编号','wsctl request 输出的编号。和邮箱二选一。'),
        field('WSCTL_EMAIL','邮箱','不走申请时直接填员工邮箱。和申请编号二选一。'),APPROVE],True,
        '开户。先留空批准码运行，看计划；再填批准码运行。结果是 workspace_created_stopped 时，用同样内容再做一遍，直到 configured。开户不发信，之后运行 wsctl deliver。'),
    'wsctl deliver':(['deliver'],[DEVICE,APPROVE],False,
        '开户后发包：一次批准同时把设备包上传到网站并发出开通邮件。先留空批准码看计划，核对收件人和邮件后填批准码执行。'),
    'wsctl reissue':(['reissue'],[DEVICE,APPROVE],False,'用原包重新上传并重发通知邮件。不换密钥，不重新开户。'),
    'wsctl renew':(['renew'],[
        field('WSCTL_EMPLOYEE','员工','邮箱或 employee_id。同一邮箱有多名员工时填 employee_id。'),
        field('WSCTL_MONTHS','月数','1–24 的整数。')],False,
        '续费。延长 paid_through，推送快照并更新网站状态。不需要批准，不重新开户，也不重发设备包。'),
    'wsctl retire':(['retire'],[
        field('WSCTL_EMPLOYEE','员工 ID','可选。只把计划缩小到这名可退役员工，不会扩大范围。改了要清空批准码重新计划。'),APPROVE],False,
        '退役。批准码留空只出计划，填计划里的 approval_sha256 才执行。永不自动运行，也没有定时任务。'),
    'wsctl access':(['access'],[APPROVE],False,'管理来源变化后重新下发 PVE 边界的 SSH 授权。'),
    'wsctl enforce':(['enforce'],[],False,'到期断开。每 5 分钟自动运行，一般不用手动点。'),
    'wsctl remind':(['remind'],[],False,'到期提醒。每小时整点自动运行，一般不用手动点。'),
    'wsctl hapi-sync':(['hapi-sync'],[],False,'让 VM500、PVE 9443 授权和 Access 策略与员工名单一致，清理退役残留。每天自动运行，一般不用手动点。'),
    'wsctl publish-status':(['publish-status'],[],False,'把状态推到网站。每小时第 15 分自动运行，一般不用手动点。'),
    'wsctl ga2-sync':(['ga2-sync'],[],False,'把网站上的 VPN 连接租约同步成 GA2 的放行规则，只动描述以 ga2-lease 开头的规则。每分钟自动运行，一般不用手动点。'),
}
SCHEDULES={'wsctl status':'*/30 * * * *','wsctl enforce':'*/5 * * * *','wsctl remind':'0 * * * *','wsctl publish-status':'15 * * * *','wsctl hapi-sync':'45 3 * * *','wsctl ga2-sync':'* * * * *'}

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

def same(current,wanted):
    # The API leaves out empty fields, so compare what remains.
    shape=lambda rows:[{k:v for k,v in row.items() if v} for row in rows or []]
    return (current.get('description')==wanted['description'] and
            shape(current.get('survey_vars'))==shape(wanted['survey_vars']) and
            bool(current.get('allow_override_args_in_task'))==wanted['allow_override_args_in_task'])

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
    for name,(arguments,survey,override,description) in TEMPLATES.items():
        wanted={'description':description,'survey_vars':survey,'allow_override_args_in_task':override}
        tid,c=ensure(p+'/templates',name,{'name':name,'project_id':project,'app':'bash','playbook':SCRIPT,
            'repository_id':repo,'environment_id':env,'inventory_id':inv,'arguments':json.dumps(arguments),'type':'',**wanted})
        changed|=c
        current=call('GET',p+f'/templates/{tid}')
        if not same(current,wanted):
            call('PUT',p+f'/templates/{tid}',{**current,**wanted});changed=True
        if name in SCHEDULES:
            _,c=ensure(p+'/schedules',name,{'name':name,'project_id':project,'template_id':tid,'cron_format':SCHEDULES[name],'active':True});changed|=c
    print(json.dumps({'changed':changed,'project_id':project}))

if __name__=='__main__':main()
