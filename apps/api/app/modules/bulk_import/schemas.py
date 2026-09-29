from pydantic import BaseModel


class RowError(BaseModel):
    row: int  # 1-indexed, counting the header as row 0 - matches what a user sees in a spreadsheet
    error: str


class BulkImportResult(BaseModel):
    """Spec §73's flow is Upload -> Validate -> Preview -> Show errors ->
    Confirm -> Import. This one shape serves both steps: called with
    dry_run=true it's the 'preview' (nothing written, `imported` stays 0);
    called with dry_run=false it's the 'confirm' (valid rows are actually
    written; already-reported invalid rows are skipped, not retried) -
    spec §73's explicit rule: 'Never blindly import invalid records.'"""
    dry_run: bool
    total_rows: int
    valid_rows: int
    imported: int
    errors: list[RowError]
