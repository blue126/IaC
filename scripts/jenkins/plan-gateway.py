#!/usr/bin/python3
"""GET-only Proxmox broker. Routes and response schemas are administrator-owned."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from control import NoRedirect, Refused, private_file, secret_file


def route(path, policy, upstream_alias=None):
    parsed=urllib.parse.urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment or '%' in parsed.path or '\\' in parsed.path:
        raise Refused('noncanonical broker path')
    if upstream_alias is not None:
        if upstream_alias not in policy['upstreams'] or not parsed.path.startswith('/api2/json'):
            raise Refused('unknown projected authorization alias')
        path='/'+upstream_alias+path
        parsed=urllib.parse.urlsplit(path)
    match=re.fullmatch(r'/([^/]+)(/api2/json(?:/[A-Za-z0-9_.:-]+)*)',parsed.path)
    if not match or match[1] not in policy['upstreams']:
        raise Refused('unknown upstream alias')
    alias, resource=match.groups()
    # No API path is admitted without an exact reviewed response schema.
    routes=policy['routes']
    matches=[item for item in routes if re.fullmatch(item['path'],resource)]
    if len(matches)!=1:
        raise Refused('provider Read route has no audited adapter')
    adapter=matches[0]
    query=urllib.parse.parse_qs(parsed.query,strict_parsing=True,keep_blank_values=True)
    if any(len(values)!=1 or key not in adapter.get('query',{}) or values[0] not in adapter['query'][key]
           for key,values in query.items()):
        raise Refused('query is outside fixed read policy')
    if '/query-url-metadata' in resource:
        if {'alias':alias,'node':resource.split('/')[4],'query':{key:values[0] for key,values in query.items()}} not in policy.get('download_probes',[]):
            raise Refused('download probe has no tested fixed adaptation')
    node=re.search(r'/nodes/([^/]+)',resource)
    if node and node[1] not in policy['upstreams'][alias]['nodes']:
        raise Refused('node outside upstream scope')
    vmid=re.search(r'/(?:lxc|qemu)/(\d+)',resource)
    allowed_vmids=policy['vmids'].get(alias,{}).get(node[1],[]) if node and isinstance(policy['vmids'],dict) else []
    if vmid and int(vmid[1]) not in allowed_vmids:
        raise Refused('VMID outside reviewed projection')
    storage=re.search(r'/storage/([^/]+)',resource)
    if storage and storage[1] not in policy['storages']:
        raise Refused('storage outside reviewed projection')
    return alias,resource+('?' + parsed.query if parsed.query else ''),adapter


def filter_value(value,schema):
    """Unknown keys are removed; missing required/unsupported shapes fail closed."""
    kind=schema['type']
    if 'sentinel_identity' in schema:
        from control import digest
        return 'PROJECTED_SECRET_'+digest(schema['sentinel_identity'].encode())[:24]
    if kind=='scalar':
        if value is not None and not isinstance(value,(str,int,float,bool)):raise Refused('non-scalar response field')
        return value
    if kind=='object':
        if not isinstance(value,dict):raise Refused('upstream object schema mismatch')
        required=schema.get('required',[])
        if any(key not in value for key in required):raise Refused('upstream required field missing')
        return {key:filter_value(value[key],child) for key,child in schema['properties'].items() if key in value}
    if kind=='array':
        if not isinstance(value,list):raise Refused('upstream array schema mismatch')
        return [filter_value(item,schema['items']) for item in value]
    types={'string':str,'integer':int,'number':(int,float),'boolean':bool,'null':type(None)}
    if kind not in types or not isinstance(value,types[kind]) or (kind in {'integer','number'} and isinstance(value,bool)):
        raise Refused('upstream scalar schema mismatch')
    if 'sentinel' in schema:return schema['sentinel']
    return value


class Handler(BaseHTTPRequestHandler):
    server_version='PlanBroker'
    def log_message(self,*_args):
        pass  # Paths may contain sensitive query data; root audit uses route IDs.
    def deny(self):
        self.send_error(403,'read policy refused request')
    do_POST=do_PUT=do_PATCH=do_DELETE=do_CONNECT=do_OPTIONS=do_HEAD=deny
    def do_GET(self):
        try:
            projected_token=self.headers.get('Authorization','')
            match=re.fullmatch(r'PVEAPIToken=projection@pve!(primary|pve2)=projection',projected_token)
            if not match:raise Refused('invalid projected authorization')
            alias,path,adapter=route(self.path,self.server.policy,match[1])
            upstream=self.server.policy['upstreams'][alias]
            origin=urllib.parse.urlsplit(upstream['origin'])
            if origin.scheme!='https' or origin.path not in {'','/'} or origin.username or origin.query:
                raise Refused('fixed HTTPS origin required')
            if adapter.get('adaptation')=='fixed-image-head':
                query=urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
                image=query['url'][0]
                request=urllib.request.Request(image,method='HEAD')
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=adapter.get('metadata_ca_file'))))
                with opener.open(request,timeout=15) as metadata:
                    projected={'data':{'filename':urllib.parse.urlsplit(image).path.rsplit('/',1)[-1],
                               'mimetype':metadata.headers.get('Content-Type','application/octet-stream'),
                               'size':int(metadata.headers['Content-Length'])}}
                self.reply(filter_value(projected,adapter['response']))
                return
            credential=private_file(upstream['token_file']).read_text().strip()
            request=urllib.request.Request(upstream['origin'].rstrip('/')+path,
                headers={'Authorization':'PVEAPIToken='+credential},method='GET')
            opener=urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=upstream['ca_file'])))
            with opener.open(request,timeout=15) as response:
                if response.status!=200:raise Refused('upstream did not return success')
                content=response.read(8*1024*1024+1)
                if len(content)>8*1024*1024:raise Refused('upstream response too large')
                decoded=json.loads(content)
                resource=urllib.parse.urlsplit(path).path
                node=re.search(r'/nodes/([^/]+)',resource)
                if resource=='/api2/json/cluster/resources':
                    decoded['data']=[item for item in decoded['data'] if item.get('vmid') in self.server.policy['vmids'].get(alias,{}).get(item.get('node'),[])]
                if resource.endswith('/qemu'):
                    allowed=self.server.policy['vmids'].get(alias,{}).get(node[1],[])+self.server.policy.get('template_vmids',{}).get(alias,{}).get(node[1],[])
                    decoded['data']=[item for item in decoded['data'] if item.get('vmid') in allowed]
                if resource.endswith('/content'):
                    decoded['data']=[item for item in decoded['data'] if item.get('volid') in self.server.policy['file_ids']]
                projected=filter_value(decoded,adapter['response'])
            self.reply(projected)
        except Exception:
            self.deny()

    def reply(self,projected):
            body=json.dumps(projected,separators=(',',':')).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--policy',required=True)
    parser.add_argument('--cert',required=True)
    parser.add_argument('--key',required=True)
    args=parser.parse_args()
    policy=json.loads(private_file(args.policy).read_text())
    if policy.get('enabled') is not True or not policy.get('routes'):
        raise Refused('broker requires a reviewed provider Read policy')
    for upstream in policy['upstreams'].values():
        secret_file(upstream['token_file']);ssl.create_default_context(cafile=upstream['ca_file'])
    secret_file(args.key)
    server=ThreadingHTTPServer((policy['listen_ip'],9443),Handler)
    server.policy=policy
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.cert,args.key)
    server.socket=context.wrap_socket(server.socket,server_side=True)
    server.serve_forever()


if __name__=='__main__':main()
