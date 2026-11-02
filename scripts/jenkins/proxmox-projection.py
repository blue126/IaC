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
PUBLIC_FILES={'proxmox/terraform.auto.tfvars','proxmox/employee-access.auto.tfvars.json','proxmox/provisioning.auto.tfvars.json'}
TEMPLATE_FILES=set()
# The OCI Hub roster is executor runtime state outside Git; the policy projects it as {}.
RUNTIME_FILES={'secrets.auto.tfvars','oci-hub-workspaces.auto.tfvars.json'}
# Legacy employee fields remain only to validate pre-retirement state inventory values.
EMPLOYEE_FIELDS=dict.fromkeys('bridge address gateway mac_address gateway_mac disk_size baseline_id bootstrap_file'.split(),'string')
EMPLOYEE_FIELDS.update(dict.fromkeys('nic_slot vmid cores memory template_id'.split(),'number'))
EMPLOYEE_FIELDS.update(dict.fromkeys('disabled retired oci_hub_managed start_ready hook_bound'.split(),'bool'))
ACCESS_FIELDS=dict.fromkeys('node pve_inventory_host storage_pool uplink_bridge uplink_address uplink_gateway uplink_mac dns_server snippet_datastore'.split(),'string')
ACCESS_FIELDS.update(dict.fromkeys('vmid template_id'.split(),'number'));ACCESS_FIELDS.update(boundary_ready='bool',legacy_gateway_retired='bool',admin_public_keys=['list','string'])
ALLOCATION_FIELDS=dict.fromkeys('node bridge address gateway mac_address gateway_mac dns_server'.split(),'string');ALLOCATION_FIELDS['nic_slot']='number'


def checked(value,kind):
    """Validate exact public cty shapes; never admit arbitrary nested maps."""
    if value is None:return value
    if isinstance(kind,dict):
        if not isinstance(value,dict) or set(value)-set(kind):raise Refused('unknown public object fields')
        return {key:checked(child,kind[key]) for key,child in value.items()}
    if isinstance(kind,list):
        if kind[0]=='object':return checked(value,kind[1])
        if kind[0]=='map':
            if not isinstance(value,dict) or any(not re.fullmatch('[a-z][a-z0-9-]{0,19}',key) for key in value):raise Refused('public roster shape mismatch')
            return {key:checked(child,kind[1]) for key,child in value.items()}
        if not isinstance(value,list):raise Refused('public list shape mismatch')
        return [checked(child,kind[1]) for child in value]
    if kind=='string' and isinstance(value,str):return value
    if kind=='bool' and isinstance(value,bool):return value
    if kind=='number' and isinstance(value,(int,float)) and not isinstance(value,bool):return value
    raise Refused('public value type mismatch')


def public_inputs(path,relative):
    if relative.endswith('.json'):values=json.loads(path.read_text())
    else:
        values={};tokens=lex(path.read_text());i=0
        while i<len(tokens):
            key=tokens[i][0]
            if i+2>=len(tokens) or tokens[i+1][0]!='=' or key in values:raise Refused('unsupported public native input')
            raw=tokens[i+2][0]
            try:values[key]=json.loads(raw)
            except Exception as error:raise Refused('nonliteral public native input') from error
            i+=3
    kinds={'pm_api_url':'string','pm_api_url_pve2':'string','target_node':'string','storage_pool':'string','pnetlab_ip_allocation_confirmed':'bool',
           'employee_access':ACCESS_FIELDS,
           'netbox_provisioned_vms':['list',{'name':'string','target_node':'string','template':'string','cores':'number','memory':'number','disk_size':'string','ip_address':'string','vmid':'number','cloudinit_slot':'string'}]}
    expected={'proxmox/terraform.auto.tfvars':{'pm_api_url','pm_api_url_pve2','target_node','storage_pool','pnetlab_ip_allocation_confirmed'},'proxmox/employee-access.auto.tfvars.json':{'employee_access'},'proxmox/provisioning.auto.tfvars.json':{'netbox_provisioned_vms'}}[relative]
    if set(values)!=expected:raise Refused('public input keys changed')
    values=checked(values,kinds)
    # Public key equality is deliberately outside the predictive contract.
    if values.get('employee_access'):values['employee_access']['admin_public_keys']=[]
    return values


INVENTORY_FIELDS=dict.fromkeys(('employee_workspace_id employee_workspace_disabled employee_workspace_vmid employee_workspace_pve_host employee_workspace_gateway employee_workspace_baseline_id employee_workspace_profile oci_hub_spoke_address employee_access_pve_host employee_access_vmid employee_access_legacy_gateway_retired employee_access_uplink_mac employee_access_uplink_address employee_access_uplink_gateway employee_access_dns_server employee_workspace_admin_public_keys_json employee_access_admin_public_keys_json employee_access_networks_json').split(),'string')


def validate_inventory(name,value):
    checked(value,'string')
    if name.endswith('admin_public_keys_json'):checked(json.loads(value),['list','string'])
    if name=='employee_access_networks_json':
        fields=dict(EMPLOYEE_FIELDS,interface='string',gateway_nic='number',ip='string',gateway_address='string')
        checked(json.loads(value),['map',fields])


def sentinel(identity):return 'PROJECTED_SECRET_'+digest(identity.encode())[:24]


def lex(text):
    """Token offsets only; expressions remain byte-for-byte native HCL."""
    tokens=[];position=0
    pattern=re.compile(r'\s+|\#[^\n]*|//[^\n]*|/\*.*?\*/|"(?:[^"\\]|\\.)*"|[A-Za-z_][A-Za-z0-9_-]*|.',re.S)
    while position<len(text):
        match=pattern.match(text,position);value=match[0];position=match.end()
        if value=='<' and text[match.start():].startswith('<<'):
            opening=re.match(r'<<-?([A-Za-z_][A-Za-z0-9_]*)[^\S\n]*\n',text[match.start():])
            if not opening:raise Refused('invalid static heredoc')
            ending=re.search(r'(?m)^\s*'+re.escape(opening[1])+r'[^\S\n]*(?:\n|$)',text[match.start()+opening.end():])
            if not ending:raise Refused('unterminated static heredoc')
            position=match.start()+opening.end()+ending.end()
            tokens.append((text[match.start():position],match.start(),position));continue
        if value.isspace() or value.startswith(('#','//','/*')):continue
        tokens.append((value,match.start(),position))
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
    if re.search(r'\bsource_file\s*{',text):raise Refused('local/URL source_file is outside projection')
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
        elif kind=='resource' and labels[0]=='proxmox_virtual_environment_file':
            tokens=lex(body);updates=[]
            for i,(value,start,end) in enumerate(tokens):
                if value=='data' and i+1<len(tokens) and tokens[i+1][0]=='=':
                    cursor=i+2;depth=0
                    while cursor<len(tokens):
                        token=tokens[cursor][0]
                        if cursor>i+2 and depth==0 and ('\n' in body[tokens[cursor-1][2]:tokens[cursor][1]] or token=='}'):break
                        if token in {'(', '[', '{'}:depth+=1
                        elif token in {')',']','}'}:depth-=1
                        cursor+=1
                    updates.append((start,tokens[cursor-1][2],'data = '+json.dumps(sentinel('redacted:source_raw.data'))+'\n'))
            if len(updates)!=1:raise Refused('file requires one reviewed source_raw payload')
            for start,end,value in reversed(updates):body=body[:start]+value+body[end:]
            replacement='resource '+json.dumps(labels[0])+' '+json.dumps(labels[1])+' {'+body+'}\n'
            rewrites.append({'file':relative,'field':'source_raw.data','dependency':'snippet content unverified'})
        elif kind=='resource' and labels[0]=='proxmox_virtual_environment_network_linux_bridge':
            replacement='resource '+json.dumps(labels[0])+' '+json.dumps(labels[1])+' {\n comment = '+json.dumps(sentinel('redacted:bridge.comment'))+'\n'+body+'}\n'
        elif kind=='module':
            sources=re.findall(r'\bsource\s*=\s*"([^"]+)"',body)
            if len(sources)!=1 or sources[0] not in {'../modules/'+m for m in MODULES}:
                raise Refused('module outside audited local closure')
        elif kind not in {'variable','output','resource','locals','import','moved','removed','data','terraform'}:
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
    for pattern in ['*.tftpl','*.tfvars','*.tfvars.json']:
        actual.update({str(path.relative_to(root)):path for path in (root/'proxmox').glob(pattern) if path.name not in RUNTIME_FILES})
    if set(actual)!=set(expected):raise Refused('native source closure changed')
    rewrites=[];inputs={}
    for relative,path in actual.items():
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected[relative]:
            raise Refused('source file is not the reviewed protected-main content')
        if relative in PUBLIC_FILES:
            values=public_inputs(path,relative)
            if set(values)&set(inputs):raise Refused('duplicate public input')
            inputs.update(values);continue
        if relative in TEMPLATE_FILES:continue
        projected,changes=project_file(path.read_text(),relative,policy)
        target=destination/relative
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        target.write_text(projected)
        rewrites+=changes
    inputs.update(copy.deepcopy(policy['public_inputs']))
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
            if key in attrs and key!='variables':
                try:checked(child,attrs[key]['type'])
                except Refused as error:raise Refused('state attribute type mismatch: '+path+'.'+key) from error
            if key in nested:
                if key=='source_file' and child:raise Refused('state source_file is outside projection')
                entry=nested[key]
                if child is None:output[key]=None
                elif entry['nesting_mode'] in {'list','set'}:output[key]=[transform(item,entry['block'],path+'.'+key) for item in child]
                elif entry['nesting_mode']=='single':output[key]=transform(child,entry['block'],path+'.'+key)
                else:raise Refused('unhandled state block nesting')
            elif key=='variables' and path.startswith('ansible_host'):
                if not isinstance(child,dict):raise Refused('inventory variable map schema mismatch')
                allowed={'ansible_host','ansible_user','proxmox_api_host','proxmox_api_port','proxmox_api_user'}|SECRET_FIELDS|set(INVENTORY_FIELDS)
                if set(child)-allowed:raise Refused('unknown inventory map key')
                if any(isinstance(item,(dict,list)) for item in child.values()):raise Refused('nested inventory map is unaudited')
                for name,item in child.items():
                    checked(item,'string')
                    if name in INVENTORY_FIELDS:validate_inventory(name,item)
                output[key]={name:('[]' if name.endswith('admin_public_keys_json') else item) if name in INVENTORY_FIELDS else sentinel('variable:proxmox_ssh_password') if name in SECRET_FIELDS else item for name,item in child.items()}
                rewrites.append(path+'.variables.[password keys]')
            elif key=='data' and '.source_raw' in path:
                output[key]=sentinel('redacted:source_raw.data');rewrites.append(path+'.data')
            elif key=='comment' and path.startswith('proxmox_virtual_environment_network_linux_bridge'):
                output[key]=sentinel('redacted:bridge.comment');rewrites.append(path+'.comment')
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
        if mode not in {'managed','data'}:raise Refused('unknown state resource mode')
        if mode=='data':
            if kind not in ALLOWED_DATA:raise Refused('unaudited state data source')
            definition=data_schemas.get(kind)
        else:definition=resource_schemas.get(kind)
        if kind=='terraform_data':
            if resource['name'] not in {'employee_slot','employee_retirement','openbao_testbed_authorization','pnetlab_allocation'}:raise Refused('unknown terraform_data resource')
            fields={'employee_slot':ALLOCATION_FIELDS,'employee_retirement':{'employee_id':'string','vmid':'number'}}.get(resource['name'])
            for instance in resource['instances']:
                if set(instance)-{'schema_version','attributes','sensitive_attributes','dependencies','index_key'} or instance.get('schema_version')!=0:raise Refused('unknown terraform_data envelope')
                attrs=instance['attributes']
                checked(attrs.get('id'),'string')
                if set(attrs)-{'id','input','output','triggers_replace'} or attrs.get('triggers_replace') is not None:raise Refused('unknown terraform_data schema')
                for key in ['input','output']:
                    payload=attrs.get(key)
                    if payload is None:continue
                    if fields is None or set(payload)!={'value','type'}:raise Refused('unaudited terraform_data payload')
                    if payload['type']!=['object',fields] or set(payload['value'])!=set(fields):raise Refused('terraform_data cty schema mismatch')
                    checked(payload['value'],fields)
                instance.pop('sensitive_attributes',None)
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
        if name=='openbao_testbed_identifiers':
            fields={'bao':{'ip':'string','name':'string','vmid':'number'},'trusted_control':{'ip':'string','name':'string','vmid':'number'}}
            if set(output)-{'value','type','sensitive'} or output.get('sensitive') or output.get('type')!=['object',{key:['object',value] for key,value in fields.items()}] or set(output['value'])!=set(fields):raise Refused('OpenBao output schema mismatch')
            for key,value in output['value'].items():
                if set(value)!=set(fields[key]):raise Refused('OpenBao identifiers incomplete')
            checked(output['value'],fields);continue
        if output.get('sensitive') or not name.endswith('_ip') or not isinstance(output.get('value'),str):
            raise Refused('nested/sensitive/unaudited root output')
    return result,rewrites
