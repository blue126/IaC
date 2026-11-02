#!/usr/bin/python3
"""Read-only CT110 allocation check. Conflicting resources are never adopted."""
import argparse
import json
import ssl
import time
import urllib.request
from control import NoRedirect, Refused,atomic_json,private_file,sign

TARGET={'node':'pve0','vmid':110,'ip':'192.168.1.110/24','name':'jenkins-agent',
        'template':'debian-12-standard_12.12-1_amd64.tar.zst','storage':'vmdata','cores':2,'memory':2048,'disk_gib':16}


def validate(resources,ipam,templates,storage):
    if any(int(resource.get('vmid',-1))==110 for resource in resources):
        raise Refused('VMID110 already exists; preserve it and reconcile ownership separately')
    if not isinstance(ipam,dict) or not {'count','results','next','previous'}<=set(ipam) or type(ipam['count']) is not int or ipam['count']<0 or not isinstance(ipam['results'],list) or ipam['next'] is not None or ipam['previous'] is not None:
        raise Refused('IPAM response is malformed or incomplete/paginated')
    if ipam['count'] or ipam['results']:
        raise Refused('IPAM already contains the requested address; allocation requires operator reconciliation')
    if not any(item.get('volid')=='local:vztmpl/'+TARGET['template'] for item in templates):
        raise Refused('the exact Debian12 template is unavailable')
    if storage.get('active') not in {1,True} or storage.get('avail',0)<16*1024**3:
        raise Refused('vmdata is unavailable or has less than16GiB free')
    if 'rootdir' not in storage.get('content','').split(','):
        raise Refused('vmdata does not support LXC rootfs')
    return TARGET


def get(url,credential,ca=None,header='Authorization'):
    if not url.startswith('https://'):raise Refused('preflight upstream requires fixed HTTPS')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=ca)))
    request=urllib.request.Request(url,headers={header:credential},method='GET')
    with opener.open(request,timeout=20) as response:return json.load(response)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--policy',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    policy=json.loads(private_file(args.policy).read_text())
    base=policy['pve_origin'].rstrip('/')+'/api2/json'
    credential='PVEAPIToken='+private_file(policy['pve_read_token']).read_text().strip()
    def pve(path):return get(base+path,credential,policy['pve_ca'])['data']
    ipam=get(policy['netbox_origin'].rstrip('/')+'/api/ipam/ip-addresses/?address=192.168.1.110',
             'Token '+private_file(policy['netbox_read_token']).read_text().strip(),policy.get('netbox_ca'))
    target=validate(pve('/cluster/resources?type=vm'),ipam,pve('/nodes/pve0/storage/local/content?content=vztmpl'),pve('/nodes/pve0/storage/vmdata/status'))
    now=int(time.time())
    report={'purpose':'peer-allocation-preflight','target':target,'nonce':policy['nonce'],
            'operator':policy['operator'],'authorization_id':policy['authorization_id'],'reason':'AD-9 first peer bootstrap',
            'issued_at':now,'expires_at':now+900,'observations':{'vmid_unallocated':True,'ipam_unallocated':True,'template_verified':True,'storage_verified':True}}
    atomic_json(args.output,sign(report,policy['key_id'],policy['signing_key']))


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('peer allocation preflight refused; preserve the existing controller entry')
