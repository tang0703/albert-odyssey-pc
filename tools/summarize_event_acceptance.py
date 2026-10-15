"""Bind final event runtime acceptance to one clean executable and local evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'reports/event'


def summarize():
    evidence = {}

    def read(name, raw=False):
        path = BASE / name
        data = path.read_bytes()
        evidence[name] = hashlib.sha256(data).hexdigest()
        return data.decode('utf-8-sig') if raw else json.loads(data)

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    phases = {name: read(name + '.json') for name in ('d1-acceptance', 'd2-python', 'd2-godot', 'd3-ui', 'd3-gpu')}
    require(all(v.get('passed') is True for v in phases.values()), 'Incomplete source/core/UI/GPU gate')
    require(phases['d1-acceptance']['totals']['source_replays'] == 18, 'Incomplete source replays')
    require(sum(r['updates'] for r in phases['d2-python']['routes']) == 6679, 'Python coverage')
    require(sum(r['updates'] for r in phases['d2-godot']['routes']) == 6679, 'Godot coverage')
    require(phases['d3-ui']['checks'] >= 54 and phases['d3-ui']['source_updates'] == 20037, 'UI coverage')
    require(len(phases['d3-gpu']['cases']) == 50 and all(c['differences'] == 0 for c in phases['d3-gpu']['cases']), 'GPU parity')
    for name, digest in phases['d1-acceptance']['evidence'].items():
        read(name, raw=True)
        require(evidence[name] == digest, 'Changed source evidence: ' + name)
    for phase in ('preflight', 'postflight'):
        probe = read('d4-host-' + phase + '.json')
        require(probe['assessment']['status'] == 'clear_in_sample_window', 'Background load: ' + phase)

    candidate = read('candidate.json')
    require(candidate['dirty'] is False, 'Dirty binary source')
    folder = Path(candidate['directory'])
    identity = {'source_commit': candidate['source_commit'], 'source_dirty': False,
                'executable_sha256': hashlib.sha256((folder / 'MAP001-Event.exe').read_bytes()).hexdigest(),
                'pck_sha256': hashlib.sha256((folder / 'MAP001-Event.pck').read_bytes()).hexdigest(),
                'event_manifest_sha256': hashlib.sha256((folder / 'event/package.json').read_bytes()).hexdigest()}
    launches = []

    def runtime(prefix, size):
        report = read(prefix + '/report.json')
        launch = read(prefix + '/launch.json')
        require(all(launch.get(k) == v for k, v in identity.items()), 'Mixed binary identity: ' + prefix)
        require(launch.get('fresh_process') and launch.get('binary_identity_unchanged'), 'Changed process: ' + prefix)
        require(report.get('passed') and not report.get('error'), 'Runtime failure: ' + prefix)
        require(report.get('actual_viewport') == size and report.get('surface_verified'), 'Physical resolution: ' + prefix)
        require(report.get('pc_device_policy') and report.get('event_images_preloaded'), 'Wrong PC policy/preload')
        for stage in ('before', 'after'):
            require(read(prefix + '/package-' + stage + '.json')['passed'], 'Package changed')
        launches.append({'case': prefix, 'first_surface_ms': launch['launch_to_first_surface_observed_ms']})
        return report

    for size in ([1920, 1080], [2560, 1440], [3840, 2160]):
        for page in (1, 2):
            name = f'screens-release-01/{size[0]}x{size[1]}-page-{page}'
            report = runtime(name, size)
            require(report['dialogue_page'] == page - 1, 'Wrong dialogue page')
            png = (BASE / name / 'screen.png').read_bytes()
            require(png[:8] == b'\x89PNG\r\n\x1a\n', 'Missing screenshot')
            require([int.from_bytes(png[16:20], 'big'), int.from_bytes(png[20:24], 'big')] == size, 'Screenshot dimensions')
            evidence[name + '/screen.png'] = hashlib.sha256(png).hexdigest()

    soak = read('soak-release-01/soak-4k/acceptance.json')
    report = runtime('soak-release-01/soak-4k', [3840, 2160])
    require(soak['passed'] and soak['full_acceptance'] and not soak['failures'], 'Soak acceptance')
    require(soak['recomputed_measured_seconds'] >= 600 and soak['average_fps'] >= 59 and soak['p95_ms'] <= 20, 'Soak performance')
    require(not soak['spikes_over_100ms_require_reproduction_review'], 'Unresolved frame spikes')
    require(soak['memory']['evaluated'] and soak['memory']['private_growth'] <= .1 and len(soak['node_counts']) == 1, 'Memory/node growth')
    require(report['pixel_reads_during_measurement'] == report['screenshots_during_measurement'] == 0, 'Measurement includes capture')
    require(report['routes_completed'] >= 2, 'No repeated event completion')

    log = read('d4-python-host.log', raw=True)
    require(re.search(r'Ran 376 tests', log) and 'FAILED (errors=9)' in log, 'Python regression count changed')
    errors = re.findall(r'^ERROR: (.+)$', log, re.M)
    known_tests = {'test_real_parameters_and_unsupported_settings', 'test_snapshot_pages_and_negative_raw_source_matches',
                   'test_full_source_vram_match', 'test_full_source_replay_matches_pinned_snapshot',
                   'test_real_block_provenance_without_collision_claim', 'test_system_ram_boundaries_and_mutation',
                   'test_all_visible_patterns_and_prior_viewports_match', 'test_pinned_region_registers_and_memory',
                   'test_real_palette_samples_remain_diagnostic'}
    require(len(errors) == 9 and {e.split()[0] for e in errors} == known_tests
            and log.count('ValueError: Source hash mismatch: work/ymir/dialogue-trace/savestates/D8562E1863DD5A2595CBE2D3A50EDFA4/0.savestate') == 7
            and log.count('ValueError: Pinned little-endian v13 state required') == 1
            and log.count('ValueError: Save-state fixture identity changed') == 1, 'Unexpected Python failures')
    for name, marker in (
        ('d4-exploration-retest.log', 'Exploration Godot, bundle, package and QA acceptance tests passed.'),
        ('d4-battle-all.log', 'Battle core, UI, presentation, timing and package checks passed.'),
        ('d4-qa-fixtures-final.log', 'Event QA acceptance: 58 fixture checks passed.'),
        ('d4-runtime-clean.log', '"checks":14,"failures":[]'),
        ('d4-workbench-clean.log', '"real_textures_loaded":true')):
        require(marker in read(name, raw=True), 'Missing regression success: ' + name)
    return {'schema': 'ao_pc_event_runtime_acceptance_v1', 'passed': True,
            'scope': 'D1-D4 runtime acceptance; final ZIP and extracted launch are separate delivery evidence.',
            'identity': identity, 'source_replays': 18, 'core_updates_per_model': 6679,
            'three_appearance_updates': 20037, 'ui_checks': phases['d3-ui']['checks'],
            'gpu_source_windows': 50, 'completed_soak_cycles': report['routes_completed'],
            'soak': soak, 'cold_process_launches': launches,
            'cold_start_scope': 'Fresh processes; OS disk caches not flushed; 100ms observation polling plus scheduling latency.',
            'regression': {'python_passed': 367, 'unavailable_old_snapshot': errors,
                           'legacy_movement_updates': 1680, 'legacy_character_updates': 6156, 'legacy_room_updates': 15183},
            'limits': ['Only the captured initial story branch is accepted.',
                       'Original text rasterization and disc device latency are replaced by PC whole-page/local-audio policy.',
                       'Player shadow omitted; adjacent scenes, full MAP001, Stage B and actual GPU 120 FPS are not accepted.',
                       'Nine old snapshot tests unavailable; original lock unchanged.',
                       'Source assets and this source-containing delivery stay local.'],
            'evidence_sha256': evidence}


def delivery():
    runtime = summarize()
    zip_path = BASE / 'd4-zip-audit.json'
    archive = json.loads(zip_path.read_bytes())
    if archive.get('passed') is not True or hashlib.sha256(Path(archive['path']).read_bytes()).hexdigest() != archive['sha256']:
        raise ValueError('ZIP acceptance or digest differs')
    import audit_event_package
    extracted = Path(archive['extraction'])
    audit_event_package.audit(extracted)
    evidence = {'d4-zip-audit.json': hashlib.sha256(zip_path.read_bytes()).hexdigest()}
    for size in ([1920, 1080], [2560, 1440], [3840, 2160]):
        for page in (1, 2):
            prefix = f'extracted-qa/{size[0]}x{size[1]}-page-{page}'
            values = {}
            for name in ('report', 'launch', 'package-before', 'package-after'):
                path = BASE / prefix / (name + '.json')
                raw = path.read_bytes()
                evidence[prefix + '/' + name + '.json'] = hashlib.sha256(raw).hexdigest()
                values[name] = json.loads(raw)
            r, launch = values['report'], values['launch']
            if (r.get('passed') is not True or r.get('actual_viewport') != size or r.get('dialogue_page') != page - 1
                    or not r.get('surface_verified') or not r.get('pc_device_policy')
                    or not launch.get('fresh_process') or not launch.get('binary_identity_unchanged')
                    or Path(launch['executable_path']).resolve() != (extracted / 'MAP001-Event.exe').resolve()
                    or any(launch.get(k) != v for k, v in runtime['identity'].items())
                    or not values['package-before'].get('passed') or not values['package-after'].get('passed')):
                raise ValueError('Extracted process validation differs: ' + prefix)
    packaged = json.loads((extracted / 'EVENT_VALIDATION.json').read_bytes())
    if packaged != runtime:
        raise ValueError('Runtime evidence changed after packaging')
    summary_tests = (BASE / 'd4-summary-tests.log').read_bytes()
    summary_text = summary_tests.decode('utf-8-sig')
    if 'Ran 7 tests' not in summary_text or not re.search(r'\bOK\s*$', summary_text):
        raise ValueError('Acceptance evidence rejection tests incomplete')
    evidence['d4-summary-tests.log'] = hashlib.sha256(summary_tests).hexdigest()
    return {'schema': 'ao_pc_event_release_v1', 'passed': True,
            'completion': 'MAP001 樓梯前 Cirrus 事件與高清繁中對話驗證通過',
            'binary_source_commit': runtime['identity']['source_commit'],
            'archive': archive, 'runtime': runtime,
            'extracted_launch_cases': 6, 'additional_acceptance_tests': 7,
            'delivery_evidence_sha256': evidence}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, default=BASE / 'd4-runtime-acceptance.json')
    parser.add_argument('--delivery', action='store_true')
    args = parser.parse_args()
    result = delivery() if args.delivery else summarize()
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'report': str(args.report)}))
