"""Read-only local acceptance; never persist captures, plots or measurements."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from kardiaos.recording import load_recording
from kardiaos.automatic_analysis import automatic_analysis
from kardiaos.report import page_plan, pdf_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    files = sorted(args.folder.glob('*.kardia'))
    if not files:
        raise SystemExit('No .kardia files in the supplied directory.')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QCoreApplication,QEvent
    from kardiaos.preview import render_page
    from kardiaos.analysis_dialog import AutomaticAnalysisDialog
    app = QApplication.instance() or QApplication([])
    totals = dict(cases=len(files), passed=0, six_lead_cases=0, one_lead_cases=0, model_runs=0)
    timings=[]
    for index, path in enumerate(files, 1):
        digest = hashlib.sha256(path.read_bytes()).digest()
        r = load_recording(path)
        original = r.raw.copy()
        started=time.perf_counter()
        result = automatic_analysis(r)
        dialog=AutomaticAnalysisDialog(r,autostart=False)
        dialog.update_result(dict(kind='measurements',value=result['measurements']))
        dialog.on_result(result);dialog.tabs.setCurrentIndex(1);dialog.show();app.processEvents()
        assert not dialog.grab().isNull()
        timings.append(time.perf_counter()-started);dialog.close();dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
        assert timings[-1]<2, 'Rules and rendered result exceeded the 2-second target'
        assert not result['scenarios'] and result['classification'], 'Neural model used by default'
        assert result['status'] == 'completed', 'Analysis incomplete'
        expected = 6 if np.any(r.lead_modes[:r.n] == 6) else 1
        reps = result['representative']
        assert len(reps) == expected, 'Missing representative curves'
        first = reps['I']
        for rep in reps.values():
            assert rep['source_centers'] == first['source_centers'], 'Unshared beat centers'
            assert rep['translation_samples'] == first['translation_samples'], 'Unshared translations'
            assert rep['markers'] == first['markers'], 'Unshared global boundaries'
            np.testing.assert_allclose(rep['unsmoothed_values_mv'], np.median(rep['aligned_beats_mv'], axis=0))
            original_median = np.asarray(rep['unsmoothed_values_mv'])
            assert max(abs(np.asarray(rep['values_mv']) - original_median)) <= .015 * np.ptp(original_median) + 1e-12
        m = result['measurements']
        assert m['pipeline']['detector_source'] == 'displayed_smoothed_medians'
        assert m['global_intervals'] and not m['fiducials'], 'Individual delineation leaked'
        assert m['duration_seconds'] > 10, 'Measurements restricted to report window'
        assert not result['qt']['neural_segmenter_used'], 'Old QT path used'
        for model in result['scenarios']:
            assert model['scores'], 'Model inference failed'
            assert model['last_sample_exclusive'] - model['first_sample'] == 3000
            totals['model_runs'] += 1
        plan = page_plan(r, analysis=result)
        assert sum(bool(row['template']) for row in plan['rows']) == expected
        assert not render_page(pdf_bytes(r, analysis=result)).isNull(), 'PDF rendering failed'
        app.processEvents()
        np.testing.assert_array_equal(r.raw, original)
        assert hashlib.sha256(path.read_bytes()).digest() == digest, 'Original file changed'
        totals['passed'] += 1
        totals['six_lead_cases' if expected == 6 else 'one_lead_cases'] += 1
        print(json.dumps(dict(case=index, status='passed', representative_curves=expected)), flush=True)
    totals.update(max_analysis_and_ui_seconds=round(max(timings),3),median_analysis_and_ui_seconds=round(float(np.median(timings)),3))
    print(json.dumps(totals), flush=True)


if __name__ == '__main__':
    main()
