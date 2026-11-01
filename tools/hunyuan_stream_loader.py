"""Load hash-verified safetensors incrementally, avoiding a 4.9 GB Windows mmap.

Use the official safetensors decoder for every tensor; preserve strict parameter
coverage and shape validation. No pickle, source edits, quantization or downloads.
"""
import gc, json, struct

def load_pipeline(model_folder):
    import torch, yaml
    from accelerate import init_empty_weights
    from accelerate.utils import set_module_tensor_to_device
    from safetensors.torch import load
    from hy3dgen.shapegen.pipelines import instantiate_from_config, Hunyuan3DDiTFlowMatchingPipeline
    folder = model_folder / 'hunyuan3d-dit-v2-mv'
    config = yaml.safe_load((folder/'config.yaml').read_text())
    modules = {}
    for name in ('model','vae','conditioner'):
        with init_empty_weights():
            modules[name] = instantiate_from_config(config[name])
    # The published checkpoint omits the training-only point-cloud encoder.
    # Official inference calls VAE.forward / latents2mesh, never VAE.encode.
    # Remove these unused meta modules instead of inventing random weights.
    del modules['vae'].encoder
    del modules['vae'].pre_kl
    expected = {f'{name}.{key}': tuple(value.shape) for name, module in modules.items() for key,value in module.state_dict().items()}
    with (folder/'model.fp16.safetensors').open('rb') as f:
        header_size = struct.unpack('<Q', f.read(8))[0]
        if header_size > 16*1024*1024: raise ValueError('Unexpected header size')
        header = json.loads(f.read(header_size)); base = 8+header_size
        records = {k:v for k,v in header.items() if k!='__metadata__'}
        if set(records)!=set(expected):
            raise ValueError({'missing':sorted(set(expected)-set(records)), 'extra':sorted(set(records)-set(expected))})
        for key,record in records.items():
            if tuple(record['shape'])!=expected[key]: raise ValueError('Shape mismatch '+key)
    def materialize(name):
        module=modules[name]
        print('Loading stage '+name,flush=True)
        with (folder/'model.fp16.safetensors').open('rb') as f:
          for i,(key,record) in enumerate(records.items()):
            module_name, parameter=key.split('.',1)
            if module_name!=name: continue
            start,end = record['data_offsets']
            if not 0 <= start <= end: raise ValueError('Invalid tensor offset')
            f.seek(base+start); payload=f.read(end-start)
            if len(payload)!=end-start: raise ValueError('Truncated tensor '+key)
            single={'value':{'dtype':record['dtype'],'shape':record['shape'],'data_offsets':[0,end-start]}}
            small=json.dumps(single,separators=(',',':')).encode();small+=b' '*((-len(small))%8)
            tensor=load(struct.pack('<Q',len(small))+small+payload)['value']
            set_module_tensor_to_device(module,parameter,'cuda',value=tensor,dtype=torch.float16)
            del tensor,payload
            if i%250==0: print(f'Loaded tensor {i}/{len(records)}',flush=True)
        if any(t.is_meta for t in list(module.parameters())+list(module.buffers())):
            raise ValueError('Uninitialized tensor in '+name)
        module.to(device='cuda',dtype=torch.float16).eval()
        return module
    def release(name):
        modules[name].to_empty(device='meta')
        gc.collect();torch.cuda.empty_cache()
    class StagedPipeline(Hunyuan3DDiTFlowMatchingPipeline):
        def encode_cond(self,*args,**kwargs):
            self.conditioner=materialize('conditioner')
            result=super().encode_cond(*args,**kwargs)
            release('conditioner')
            self.model=materialize('model')
            return result
        def _export(self,*args,**kwargs):
            release('model')
            self.vae=materialize('vae')
            return super()._export(*args,**kwargs)
    # Initial placeholders avoid .to() on meta tensors. The inherited inference
    # loop, scheduler, conditioning and extractor remain unchanged.
    pipeline=StagedPipeline(vae=torch.nn.Identity(),model=torch.nn.Identity(),conditioner=torch.nn.Identity(),
        scheduler=instantiate_from_config(config['scheduler']),
        image_processor=instantiate_from_config(config['image_processor']),
        device='cuda', dtype=torch.float16)
    pipeline.vae=modules['vae'];pipeline.model=modules['model'];pipeline.conditioner=modules['conditioner']
    return pipeline
