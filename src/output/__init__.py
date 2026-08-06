"""Turning approved decisions into the FMLV upload CSV.

Phase 7 (DESIGN.md §5 step 6 / TODO.md): a run's `proposed_change`/`decision` rows
(Phase 6) are the *diff*, not the upload — this package applies every accepted or
corrected decision on top of the baseline export to produce full `Motorhome` rows in
the exact FMLV column order, ready to hand-upload.
"""

from .build import (
    UploadResult,
    apply_field,
    build_upload_motorhomes,
    generate_upload,
    write_upload_csv,
)

__all__ = [
    "UploadResult",
    "apply_field",
    "build_upload_motorhomes",
    "generate_upload",
    "write_upload_csv",
]
