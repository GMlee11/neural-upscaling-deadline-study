"""Format verified corrected-runtime summaries; never launch experiments."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from artifact.paper1_hotmobile2027.verify_corrected_runtime import read_archive

ROOT = Path(__file__).resolve().parents[2]
CONTROLS = ('bicubic', 'always', 'fixed2', 'scheduler')
LABELS = {'bicubic':'Bicubic', 'always':'Always neural', 'fixed2':'Fixed/2', 'scheduler':'Deadline'}


def load_summary(path: Path, board: str) -> dict:
    summary = json.loads(path.read_text())
    assert summary['board'] == board and summary['status'] == 'COMPLETE'
    assert summary['engineering'] is False and not summary['incomplete_cells']
    assert len(summary['cells']) == 80
    assert sum(row['source_frames'] for row in summary['cells']) == 24000
    aggregate = [row for row in summary['aggregates'] if row['repetition'] is None]
    assert {(row['width'],row['control']) for row in aggregate} == {(w,c) for w in (320,640) for c in CONTROLS}
    assert len(aggregate) == 8
    assert all(row['source_frames']==3000 and row['cells']==10 for row in aggregate)
    assert all(row['completed']==row['submitted'] for row in aggregate)
    return summary


def table(summaries: list[dict]) -> str:
    lines = [
        '% Generated from the separate verified corrected-runtime V1 summaries.',
        r'\begin{table*}[t]',
        r'\caption{Corrected-system primary matrix: each row contains 3,000 source frames (five scenes, two repetitions). Receipt-side eligible means receipt age plus assignment duration $\leq33.33$ ms, excluding intervening waiting. Timely means first source-linked neural post-draw age $\leq33.33$ ms. Source rate is the equal-cell arithmetic mean of per-cell capture rates, not panel FPS. Classical zeros mean no neural work, not failed classical delivery.}',
        r'\label{tab:corrected-runtime}',
        r'\centering',
        r'\fontsize{10}{11}\selectfont',
        r'\setlength{\tabcolsep}{4pt}',
        r'\begin{tabular}{@{}lllrrrrr@{}}',
        r'\toprule',
        r'SoC & Output & Control & Sources/s & Submitted & \shortstack{Receipt-side\\eligible} & Selected & Timely \\',
        r'\midrule',
    ]
    for summary in summaries:
        rows = {(r['width'],r['control']):r for r in summary['aggregates'] if r['repetition'] is None}
        for width in (320,640):
            for index,control in enumerate(CONTROLS):
                row=rows[width,control]
                soc=summary['board'].upper() if width==320 and index==0 else ''
                output=f'{width*18//16}p' if index==0 else ''
                fields=[soc,output,LABELS[control],f"{row['equal_cell_mean_rates']['source_capture_rate']:.2f}"]
                fields.extend(f'{row[key]:,}' for key in ('submitted','eligible','selected','timely_post'))
                lines.append(' & '.join(fields)+r' \\')
            lines.append(r'\addlinespace[2pt]')
    lines.extend([r'\bottomrule',r'\end{tabular}',r'\end{table*}'])
    return '\n'.join(lines)+'\n'


def quality_table(historical: str) -> str:
    label=historical.index(r'\label{tab:confirmatory-quality}')
    start=historical.rfind(r'\begin{table*}',0,label)
    end=historical.index(r'\end{table*}',label)+len(r'\end{table*}')
    assert start>=0
    return historical[start:end]+'\n'


def timing_examples(root: Path=ROOT) -> list[dict]:
    """First eligible source in execution/source order per repetition, not by delay.

    Selection is post hoc and illustrative, not a new confirmatory estimate.
    Assignment is the log stamp just after assignment, not receipt+upload.
    """
    folder=root/'results/rk3576/paper1_corrected_runtime_v1'
    summary=load_summary(folder/'summary-v1.json','rk3576')
    files=read_archive(folder/'capture-evidence-v1.tar.gz')
    examples=[]
    for repetition in (1,2):
        cells=sorted((c for c in summary['cells'] if c['width']==320
                      and c['control']=='always' and c['repetition']==repetition),
                     key=lambda c:c['index'])
        for cell in cells:
            prefix='capture-v1/'+cell['directory']+'/'
            audit=[json.loads(line) for line in files[prefix+'composition.jsonl'].splitlines()]
            eligible=sorted((r for r in audit if r['event']=='terminal' and r['response_eligible']),
                            key=lambda r:r['source_id'])
            if not eligible:
                continue
            terminal=eligible[0]
            source=terminal['source_id']
            capture=next(r['capture_usec'] for r in audit if r['event']=='source' and r['source_id']==source)
            events=[json.loads(line) for line in files[prefix+'selection_events.jsonl'].splitlines()]
            assignment=next(r for r in events if r['event']=='assignment' and r['source_id']==source)
            draws=[r for r in audit if r['event']=='draw' and r['selected_path']=='neural'
                   and r['neural_source_id']==source]
            draw=min(draws,key=lambda r:r['post_draw_usec'])
            receipt=(assignment['worker_received_usec']-capture)/1000
            assert abs(receipt+assignment['upload_ms']-terminal['response_age_ms'])<1e-9
            assert terminal['response_age_ms']<=1000/30
            examples.append(dict(repetition=repetition,cell=cell['directory'],source_id=source,
                receipt_ms=receipt,assignment_stamp_ms=(assignment['recorded_usec']-capture)/1000,
                first_post_ms=(draw['post_draw_usec']-capture)/1000,
                upload_ms=assignment['upload_ms'],eligibility_ms=terminal['response_age_ms']))
            break
        else:
            raise AssertionError('No eligible example in repetition')
    return examples


def timing_figure(root: Path=ROOT) -> str:
    lines=[r'\newcommand{\CorrectedTimingFigure}{%',r'\begin{figure}[t]',r'\centering',
           r'\setlength{\tabcolsep}{3pt}',r'\begin{tabular}{@{}lrrrr@{}}',r'\toprule',
           r' & Capture & Receipt & Assign.$^*$ & Post-draw \\',r'\midrule']
    examples=timing_examples(root)
    for e in examples:
        lines.append(f"R{e['repetition']} & 0 & {e['receipt_ms']:.2f} & {e['assignment_stamp_ms']:.2f} & {e['first_post_ms']:.2f}"+r' \\')
    lines.extend([r'\bottomrule',r'\end{tabular}',
        r'\par\smallskip Capture $\rightarrow$ receipt $\rightarrow$ assignment $\rightarrow$ first post-draw',
        r'\par\smallskip Receipt-side scores (ms; not event timestamps)',
        r'\par Receipt age + assignment duration',r'\par\smallskip',
        r'\begin{tabular}{@{}lrlr@{}}'])
    for e in examples:
        lines.append(f"R{e['repetition']} & {e['receipt_ms']:.3f} + {e['upload_ms']:.3f} & = & {e['eligibility_ms']:.3f}"+r' \\')
    lines.extend([r'\end{tabular}',
        r'\caption{RK3576 360p always-neural examples, one per repetition (selection rule in Section~\ref{sec:delivery-results}). Elapsed event times are measured from capture; $^*$marks the stamp just after assignment. Receipt-side scores exclude intervening waiting. Both examples pass the 33.33-ms score threshold but are already late at assignment. Arrows show event order, not duration.}',
        r'\label{fig:corrected-timing}',r'\end{figure}',r'}'])
    return '\n'.join(lines)+'\n'


def generate(root: Path=ROOT) -> str:
    summaries=[load_summary(root/f'results/{board}/paper1_corrected_runtime_v1/summary-v1.json',board)
               for board in ('rk3576','rk3566')]
    historical=(root/'docs/paper/generated/paper1_hotmobile2027.tex').read_text()
    return table(summaries)+'\n'+quality_table(historical)+'\n'+timing_figure(root)


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    text=generate()
    with args.output.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(text)
    print('Generated corrected primary matrix and unchanged offline quality table')


if __name__=='__main__':
    main()
