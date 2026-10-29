#!/usr/bin/env python3
"""Finite native-HCL projection for the protected current Proxmox source closure."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
from control import Refused, digest

SECRET_VARIABLES={'pm_api_token_id','pm_api_token_secret','pm_api_token_id_pve2',
                  'pm_api_token_secret_pve2','proxmox_ssh_password','ubuntu_2604_bootstrap_password'}
SECRET_FIELDS={'password','cipassword','ansible_ssh_pass','ansible_password','ansible_become_password'}
MODULES={'proxmox-lxc','proxmox-vm','proxmox-cloud-image-vm'}
ALLOWED_DATA={'proxmox_virtual_environment_vms'}


def sentinel(identity):return 'PROJECTED_SECRET_'+digest(identity.encode())[:24]


def lex(text):
    """Token offsets only; expressions remain byte-for-byte native HCL."""
    tokens=[];position=0
    pattern=re.compile(r'\s+|\#[^\n]*|//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|[A-Za-z_][A-Za-z0-9_-]*|.',re.S)
    for match in pattern.finditer(text):
        value=match[0]
        if value.isspace() or value.startswith(('#','//','/*')):continue
        if value=='<' and text[match.start():].startswith('<<'):raise Refused('heredoc requires a separately audited adapter')
        tokens.append((value,match.start(),match.end()))
    return tokens


def blocks(text):
    tokens=lex(text);index=0;result=[]
    while index<len(tokens):
        kind,start,_=tokens[index]
        if not re.fullmatch('[A-Za-z_][A-Za-z0-9_-]*',kind):raise Refused('unexpected top-level native HCL token')
        labels=[];index+=1
        while index<len(tokens) and tokens[index][0].startswith('"'):
            labels.append(json.loads(tokens[index][0]));index+=1
        if index>=len(tokens) or tokens[index][0]!='{':raise Refused('expected native HCL block')
        opening=tokens[index][2];depth=1;index+=1
        while index<len(tokens) and depth:
            value=tokens[index][0]
            if value=='{':depth+=1
            elif value=='}':depth-=1
            if depth==0:
                result.append({'kind':kind,'labels':labels,'start':start,'end':tokens[index][2],
                               'body_start':opening,'body_end':tokens[index][1],
                               'body':text[opening:tokens[index][1]]})
            index+=1
        if depth:raise Refused('unterminated native HCL block')
    return result


def strip_cloud(body):
    # cloud is the only nested block whose removal changes backend capabilities.
    tokens=lex(body)
    for index,(value,start,_) in enumerate(tokens):
        if value=='cloud' and index+1<len(tokens) and tokens[index+1][0]=='{':
            depth=1;cursor=index+2
            while cursor<len(tokens) and depth:
                if tokens[cursor][0]=='{':depth+=1
                elif tokens[cursor][0]=='}':depth-=1
                cursor+=1
            if depth:raise Refused('unterminated cloud block')
            return body[:start]+'backend "local" { path = "projection.tfstate" }\n'+body[tokens[cursor-1][2]:]
    return body


def project_file(text,relative,policy):
    replacements=[];rewrites=[]
    for block in blocks(text):
        kind=block['kind'];labels=block['labels'];body=block['body']
        if kind in {'provisioner','connection'}:raise Refused('executable configuration refused')
        if kind=='data' and (not labels or labels[0] not in ALLOWED_DATA):raise Refused('unaudited data source')
        if re.search(r'\b(provisioner|connection)\s*["{]',body):raise Refused('embedded executable configuration')
        if kind=='variable' and re.search(r'\bsensitive\s*=\s*true\b',body) and labels[0] not in SECRET_VARIABLES|{'password','bootstrap_password'}:raise Refused('unknown sensitive input requires a paired policy')
        replacement=None
        if kind=='provider':
            if labels!=['proxmox']:raise Refused('unknown native provider')
            aliases=re.findall(r'\balias\s*=\s*"([^"]+)"',body)
            alias=aliases[0] if aliases else 'default'
            endpoint=policy['provider_aliases'][alias]
            replacement='provider "proxmox" {\n'+(' alias = '+json.dumps(alias)+'\n' if alias!='default' else '')
            replacement+=' endpoint = '+json.dumps(endpoint)+'\n api_token = '+json.dumps('projection@pve!'+('pve2' if alias.startswith('pve2') else 'primary')+'=projection')+'\n insecure = false\n}\n'
            rewrites.append({'file':relative,'field':'provider.'+alias,'dependency':'broker only; SSH removed'})
        elif kind=='terraform' and re.search(r'\bcloud\s*{',body):
            replacement='terraform {\n'+strip_cloud(body)+'\n}\n'
        elif kind=='variable' and labels[0] in SECRET_VARIABLES:
            replacement='variable '+json.dumps(labels[0])+' {\n type = string\n sensitive = true\n default = '+json.dumps(sentinel('variable:'+labels[0]))+'\n}\n'
            rewrites.append({'file':relative,'field':'variable.'+labels[0],'dependency':'secret equality unverified'})
        elif kind=='resource' and labels[0] in {'proxmox_virtual_environment_vm','proxmox_virtual_environment_container'}:
            additions=''
            if not re.search(r'^\s*description\s*=',body,re.M):additions+=' description = '+json.dumps(sentinel('redacted:description'))+'\n'
            if labels[0]=='proxmox_virtual_environment_vm':
                if re.search(r'^\s*kvm_arguments\s*=',body,re.M):raise Refused('VM args require an explicit reviewed transformation')
                additions+=' kvm_arguments = '+json.dumps(sentinel('redacted:args'))+'\n'
            if additions:replacement='resource '+json.dumps(labels[0])+' '+json.dumps(labels[1])+' {\n'+additions+body+'\n}\n'
        elif kind=='module':
            sources=re.findall(r'\bsource\s*=\s*"([^"]+)"',body)
            if len(sources)!=1 or sources[0] not in {'../modules/'+m for m in MODULES}:
                raise Refused('module outside audited local closure')
        elif kind not in {'variable','output','resource','locals','import','data','terraform'}:
            raise Refused('unknown native HCL block type')
        if kind=='output' and any(re.search(r'\bvar\.'+re.escape(secret)+r'\b',body) for secret in SECRET_VARIABLES):
            raise Refused('secret-dependent output is outside predictive scope')
        if replacement is not None:replacements.append((block['start'],block['end'],replacement))
    for start,end,replacement in reversed(replacements):text=text[:start]+replacement+text[end:]
    # Mixed inventory maps retain non-secret keys and replace only password values.
    text=re.sub(r'(\bdescription\s*=\s*)"(?:[^"\\]|\\.)*"',lambda match:match[1]+json.dumps(sentinel('redacted:description')),text)
    text,count=re.subn(r'(\bansible_ssh_pass\s*=\s*)var\.proxmox_ssh_password\b',
                       lambda match:match[1]+json.dumps(sentinel('variable:proxmox_ssh_password')),text)
    if count:rewrites.append({'file':relative,'field':'ansible_host.variables.ansible_ssh_pass','dependency':'secret equality unverified'})
    # All remaining uses are a tiny audited set of password plumbing or variable
    # declarations. Anything affecting names/cardinality/triggers is refused.
    for line in text.splitlines():
        stripped=line.strip()
        if stripped.startswith(('#','//')):continue
        for secret in SECRET_VARIABLES:
            if re.search(r'\bvar\.'+secret+r'\b',line) and not re.fullmatch(r'\s*bootstrap_password\s*=\s*var\.ubuntu_2604_bootstrap_password\s*',line):
                raise Refused('secret dependency outside audited password plumbing')
    return text,rewrites


def project_source(root,destination,policy):
    root=Path(root);destination=Path(destination)
    expected=policy['source_files']
    actual={str(p.relative_to(root)):p for directory in [root/'proxmox',*[root/'modules'/m for m in sorted(MODULES)]]
            for p in directory.glob('*.tf')}
    if set(actual)!=set(expected):raise Refused('native source closure changed')
    rewrites=[]
    for relative,path in actual.items():
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected[relative]:
            raise Refused('source file is not the reviewed protected-main content')
        projected,changes=project_file(path.read_text(),relative,policy)
        target=destination/relative
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        target.write_text(projected)
        rewrites+=changes
    inputs=copy.deepcopy(policy['public_inputs'])
    if set(inputs)&SECRET_VARIABLES:raise Refused('public input file contains secret variables')
    (destination/'proxmox'/'projection.auto.tfvars.json').write_text(json.dumps(inputs))
    return rewrites


def project_state(state,schema):
    result=copy.deepcopy(state);rewrites=[]
    if result.get('version')!=4:raise Refused('unsupported raw state schema')
    if set(result)-{'version','terraform_version','serial','lineage','outputs','resources','check_results'}:raise Refused('unknown top-level raw state fields')
    if 'check_results' in result:
        result.pop('check_results');rewrites.append('historical check diagnostics removed')
    resource_schemas={}
    data_schemas={}
    for provider in schema['provider_schemas'].values():
        resource_schemas.update(provider.get('resource_schemas',{}));data_schemas.update(provider.get('data_source_schemas',{}))
    def transform(value,block,path):
        if value is None:return None
        if not isinstance(value,dict):raise Refused('state block shape mismatch')
        attrs=block.get('attributes',{});nested=block.get('block_types',{})
        if set(value)-set(attrs)-set(nested):raise Refused('unknown state fields in '+path)
        output={}
        for key,child in value.items():
            if key in nested:
                entry=nested[key]
                if child is None:output[key]=None
                elif entry['nesting_mode'] in {'list','set'}:output[key]=[transform(item,entry['block'],path+'.'+key) for item in child]
                elif entry['nesting_mode']=='single':output[key]=transform(child,entry['block'],path+'.'+key)
                else:raise Refused('unhandled state block nesting')
            elif key=='variables' and path.startswith('ansible_host'):
                if not isinstance(child,dict):raise Refused('inventory variable map schema mismatch')
                allowed={'ansible_host','ansible_user','proxmox_api_host','proxmox_api_port','proxmox_api_user'}|SECRET_FIELDS
                if set(child)-allowed:raise Refused('unknown inventory map key')
                if any(isinstance(item,(dict,list)) for item in child.values()):raise Refused('nested inventory map is unaudited')
                output[key]={name:sentinel('variable:proxmox_ssh_password') if name in SECRET_FIELDS else item for name,item in child.items()}
                rewrites.append(path+'.variables.[password keys]')
            elif key in {'description','kvm_arguments'}:
                output[key]=sentinel('redacted:description' if key=='description' else 'redacted:args') if child is not None else None
                rewrites.append(path+'.'+key)
            elif key=='keys':
                output[key]=[] if child is not None else None
                rewrites.append(path+'.keys')
            elif attrs[key].get('sensitive') or key in SECRET_FIELDS:
                identity='variable:ubuntu_2604_bootstrap_password' if key=='password' and 'initialization' in path else path+'.'+key
                output[key]=sentinel(identity) if child is not None else None
                rewrites.append(path+'.'+key)
            else:output[key]=child
        return output
    for resource in result.get('resources',[]):
        if set(resource)-{'module','mode','type','name','provider','instances'}:raise Refused('unknown state resource envelope')
        kind=resource['type'];mode=resource['mode']
        if mode=='data':
            if kind not in ALLOWED_DATA:raise Refused('unaudited state data source')
            definition=data_schemas.get(kind)
        else:definition=resource_schemas.get(kind)
        if kind=='terraform_data':
            for instance in resource['instances']:
                if set(instance['attributes'])-{'id','input','output','triggers_replace'} or any(instance['attributes'].get(key) is not None for key in ['input','output','triggers_replace']):raise Refused('unknown terraform_data schema or secret-dependent payload')
            continue
        if definition is None:raise Refused('unknown provider resource schema')
        for instance in resource['instances']:
            if set(instance)-{'schema_version','attributes','sensitive_attributes','private','dependencies','status','deposed','index_key','create_before_destroy','identity_schema_version'}:raise Refused('unknown state instance envelope')
            if instance.get('identity_schema_version',0)!=0:raise Refused('unsupported resource identity schema')
            if instance.get('schema_version')!=definition['version']:raise Refused('resource schema version mismatch')
            if instance.get('private'):
                try:private=json.loads(base64.b64decode(instance['private'],validate=True))
                except Exception as error:raise Refused('opaque provider private state') from error
                if not isinstance(private,dict):raise Refused('unaudited provider private state')
                allowed={'original_state_size','url_size'} if kind=='proxmox_virtual_environment_download_file' else {'schema_version'}
                if set(private)-allowed:raise Refused('unaudited provider private state')
                for key,value in private.items():
                    decoded=base64.b64decode(value,validate=True).decode() if kind=='proxmox_virtual_environment_download_file' else value
                    if not isinstance(decoded,str) or not re.fullmatch(r'[0-9]{1,20}',decoded):raise Refused('provider private field has nonnumeric payload')
            instance['attributes']=transform(instance['attributes'],definition['block'],kind+'.'+resource['name'])
            instance.pop('sensitive_attributes',None)
    for name,output in result.get('outputs',{}).items():
        if output.get('sensitive') or not name.endswith('_ip') or not isinstance(output.get('value'),str):
            raise Refused('nested/sensitive/unaudited root output')
    return result,rewrites
