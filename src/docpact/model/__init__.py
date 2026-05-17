"""Data model — pure types used throughout docpact.

The shapes defined here correspond to the conceptual interface in
spec §7. They are deliberately simple (dataclasses, no behavior) so that
rule functions can be written as pure transformations.

The data model is internal API in v0.1. Spec §18.6 states that it is not
stable surface. Third-party rule plugins are not supported in v0.1
precisely to keep these types refactorable.
"""
