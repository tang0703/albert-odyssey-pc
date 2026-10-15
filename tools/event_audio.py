"""Lossless local conversion of the one source event AIFF resource to PCM WAV."""
import argparse
import hashlib
import io
import json
import struct
import wave
from pathlib import Path

SOURCE_SHA='ccca257dd4644a1dea67597d0876db11d8ddd42ed964960723e6f8938078cfaf'


def convert(source):
    if hashlib.sha256(source).hexdigest()!=SOURCE_SHA:raise ValueError('Unapproved or changed event audio')
    if source[:4]!=b'FORM' or source[8:12]!=b'AIFF' or int.from_bytes(source[4:8],'big')!=len(source)-8:
        raise ValueError('Invalid AIFF container')
    chunks={};position=12
    while position<len(source):
        if position+8>len(source):raise ValueError('Truncated AIFF chunk header')
        name=source[position:position+4];length=int.from_bytes(source[position+4:position+8],'big')
        start=position+8;end=start+length
        if end>len(source) or name in chunks:raise ValueError('Truncated or duplicate AIFF chunk')
        chunks[name]=source[start:end];position=end+(length&1)
    if set(chunks)!={b'COMM',b'SSND',b'MARK',b'INST',b'APPL'}:raise ValueError('Unexpected source AIFF chunks')
    comm=chunks[b'COMM']
    if len(comm)!=18 or comm[8:]!=bytes.fromhex('400dac44000000000000'):raise ValueError('Unsupported source sample rate')
    channels,frames,bits=struct.unpack('>HIH',comm[:8])
    if (channels,frames,bits)!=(1,15324,16):raise ValueError('Unsupported source PCM format')
    sound=chunks[b'SSND']
    if sound[:8]!=bytes(8) or len(sound)!=frames*2+8:raise ValueError('Unsupported PCM offset or length')
    pcm=sound[8:];little=bytearray(len(pcm));little[::2]=pcm[1::2];little[1::2]=pcm[::2]
    stream=io.BytesIO()
    with wave.open(stream,'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(22050);output.writeframes(little)
    result=stream.getvalue()
    with wave.open(io.BytesIO(result),'rb') as check:
        if (check.getnchannels(),check.getsampwidth(),check.getframerate(),check.getnframes())!=(1,2,22050,15324):
            raise ValueError('Converted WAV format differs')
        actual=check.readframes(frames)
        restored=bytearray(len(actual));restored[::2]=actual[1::2];restored[1::2]=actual[::2]
        if restored!=pcm:raise ValueError('PCM samples changed during conversion')
    return result,{'schema':'ao_pc_event_audio_conversion_v1','source_sha256':SOURCE_SHA,
        'output_sha256':hashlib.sha256(result).hexdigest(),'source_pcm_sha256':hashlib.sha256(pcm).hexdigest(),
        'channels':1,'sample_rate':22050,'sample_bits':16,'sample_count':frames,'duration_seconds':frames/22050,
        'conversion':'Byte-order conversion only; no resampling, normalization, trim or added voice.',
        'pcm_roundtrip_passed':True,'playback_acceptance':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();raw,report=convert(a.source.read_bytes());a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'cirrus-event.wav').write_bytes(raw)
    (a.out/'source-audio.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
