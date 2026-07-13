"""Persistence layer, hidden behind the ``TaskRepository`` interface.

Nothing outside this package knows how a Task is stored. Swapping SQLite
for another backend means implementing ``TaskRepository`` once and wiring
it in the composition root — no other code changes.
"""
