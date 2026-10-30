"""Cross-cutting security middleware and helpers (build plan section 13).

Nothing here knows about journeys or receipts: these are the controls that apply
to every request, mounted once in `app.main`.
"""
