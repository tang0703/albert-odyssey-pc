"""Deliver the frozen C2 review without external image dependencies."""
import base64
import hashlib
import io
import json
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'art/unity/player-refined-v1'
DEST = ROOT / 'art/unity/player-refined-v1-delivery'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    lock_bytes = (SOURCE / 'review-lock.json').read_bytes()
    lock = json.loads(lock_bytes)
    for name, record in lock['files'].items():
        raw = (SOURCE / name).read_bytes()
        assert len(raw) == record['bytes'] and digest(raw) == record['sha256'], name
    images = {}
    records = {}
    names = [f'review/{who}-{light}-{view}.png'
             for who in ('old', 'refined') for light in ('neutral', 'warm')
             for view in ('front', 'left', 'back', 'right', 'face')]
    names += ['review/old-room.png', 'review/refined-room.png',
              '../../enhanced25d/v1/review/directions-review.png']
    for name in names:
        raw = (SOURCE / name).read_bytes()
        expected = lock['concept_reference'] if name.startswith('../') else lock['files'][name]
        assert digest(raw) == expected['sha256'], name
        with Image.open(io.BytesIO(raw)) as picture:
            picture.verify()
        images[name] = 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')
        records[name] = {'bytes': len(raw), 'sha256': digest(raw)}

    page = (SOURCE / 'review.html').read_text(encoding='utf-8')
    page = page.replace('<h1>人物精修造型審閱</h1>',
                        '<h1>人物精修造型審閱</h1><p>圖片內嵌版：無須同目錄圖片檔。若切換按鈕無效，請展開下方「全部角度」。</p>')
    # The unchanged primary images also work when a viewer disables JavaScript.
    page = re.sub(r'(src|href)="([^"]+\.png)"',
                  lambda m: f'{m[1]}="{images[m[2]]}"', page)
    page = page.replace(".src='review/old-'+light+'-'+view+'.png'",
                        ".src=embedded['review/old-'+light+'-'+view+'.png']")
    page = page.replace(".src='review/refined-'+light+'-'+view+'.png'",
                        ".src=embedded['review/refined-'+light+'-'+view+'.png']")
    page = page.replace('<script>', '<script>const embedded=' + json.dumps(images) + ';', 1)
    # Native details remain usable without scripts, including local preview panels.
    fallback = '<h2>全部角度（不需切換按鈕）</h2>'
    for light, light_label in [('neutral', '中性光'), ('warm', '暖光')]:
        for view, label in [('front', '正面'), ('left', '左側'), ('back', '背面'), ('right', '右側'), ('face', '臉部近景')]:
            fallback += f'<details><summary>{light_label}・{label}</summary><section class="pair">'
            for who, who_label in [('old', '舊版'), ('refined', '新版')]:
                key = f'review/{who}-{light}-{view}.png'
                fallback += f'<figure><img src="{images[key]}" alt="{who_label} {light_label} {label}"><figcaption>{who_label} {light_label} {label}</figcaption></figure>'
            fallback += '</section></details>'
    page = page.replace('</main>', fallback + '</main>')
    page = re.sub(r'<a href="(?:player-[^"]+|review-lock\.json)">([^<]+)</a>', r'\1', page)
    page = page.replace('<p>可編輯網格', '<p>可編輯來源保留於原 player-refined-v1 資料夾：可編輯網格')
    # Validate every img including the non-script fallback, and the dynamic map.
    embedded_sources = re.findall(r'<img[^>]+src="([^"]+)"', page)
    for source in embedded_sources:
        assert source.startswith('data:image/png;base64,')
        raw = base64.b64decode(source.split(',', 1)[1], validate=True)
        assert digest(raw) in {record['sha256'] for record in records.values()}
    assert len(embedded_sources) == 25
    DEST.mkdir(parents=True, exist_ok=True)
    output = page.encode('utf-8')
    (DEST / 'review.html').write_bytes(output)
    manifest = {
        'schema': 'ao_character_review_delivery_v1',
        'approval_status': lock['status'], 'approved': lock['approved'],
        'source_lock_sha256': digest(lock_bytes),
        'review_html': {'bytes': len(output), 'sha256': digest(output)},
        'images': records, 'verified_source_files': len(lock['files']),
        'embedded_img_elements': len(embedded_sources),
        'external_image_dependencies': 0,
        'validation': 'Source hashes, PNG decoding, embedded byte equality and all view keys; not a target-app rendering check.',
        'performance_tested': False,
    }
    (DEST / 'delivery.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: manifest[key] for key in ('review_html', 'verified_source_files', 'embedded_img_elements', 'external_image_dependencies')}, indent=2))


if __name__ == '__main__':
    main()
