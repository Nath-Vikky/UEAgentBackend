from __future__ import annotations

from scripts.export_editor_operation_catalog import render_editor_operation_catalog


def test_render_editor_operation_catalog_contains_groups_and_safety_boundary() -> None:
    markdown = render_editor_operation_catalog()

    assert "# Editor Operation Catalog" in markdown
    assert "### Blueprint Operations" in markdown
    assert "`add_blueprint_node_template`" in markdown
    assert "`connect_blueprint_nodes`" in markdown
    assert "### UMG Operations" in markdown
    assert "`set_umg_widget_text`" in markdown
    assert "Roadmap:" in markdown
    assert "`set_umg_widget_appearance`" in markdown
    assert "`inspect_level_actors`" in markdown
    assert "Follow-up candidates are drafts and are never auto-executed." in markdown
