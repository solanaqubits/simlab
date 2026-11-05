"""Explicit verified LaTeX/Typst dispatch for PDF page consumers; no compiler execution."""
import geek_work_release_compile as latex
import geek_work_typst_gate as typst


def verified(bundle,anchor):
    latex.k.digest(anchor);raw=latex.m.read(bundle/'manifest.json');latex.m.require(latex.m.sha(raw)==anchor,'PDF input anchor mismatch')
    manifest=latex.m.load(raw);latex.m.require(type(manifest) is dict,'PDF input manifest');schema=manifest.get('schema')
    if schema=='geek-work-release-compile-binding-manifest-1':
        report,archive=latex.verified_binding(bundle,anchor)
        pdf=archive['compile/artifacts/document.pdf'] if report['pdf'] is not None else None
    elif schema=='geek-work-typst-gate-manifest-1':
        report,archive=typst.verified(bundle,anchor)
        report=dict(report,binding_kind='typst_gate',diagnostics_review_required=report['compiler_diagnostics_present'] or report['pdf'] is None)
        pdf=archive['compile/document.pdf'] if report['pdf'] is not None else None
    else:raise ValueError('unsupported verified PDF binding schema')
    return report,archive,pdf
