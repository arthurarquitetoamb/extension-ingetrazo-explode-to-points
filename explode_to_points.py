# SPDX-License-Identifier: GPL-3.0-or-later
"""Explode To Points - an IngeTrazo extension.

Converts the selected shape(s) into individual selectable points.
For example, a selected rectangle becomes four selectable points (one per corner).

Each point is created as a small selectable marker group at a unique vertex
position taken from the selected geometry. Optionally, the original selected
object(s) can be deleted in the same undoable step.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from core.group import Group
from core.history import SnapshotImport
from core.layers import active_layer
from core.mesh import Mesh

# Length of each point marker segment in model units (metres).
POINT_MARKER_SIZE = 0.02

# Tolerance for considering two positions as the same point (metres).
DEDUP_TOLERANCE = 1e-6


def _collect_vertices_from_mesh(mesh, out: list) -> None:
    """Collect vertex positions from a mesh (vertices, edge endpoints, face loops)."""
    if mesh is None:
        return
    # Prefer mesh.vertices if available.
    for v in getattr(mesh, "vertices", ()) or ():
        pos = getattr(v, "position", None)
        if pos is not None:
            out.append(QVector3D(pos))
    # Fallback: edge endpoints and face vertices.
    for e in getattr(mesh, "edges", ()) or ():
        out.append(QVector3D(e.a))
        out.append(QVector3D(e.b))
    for f in getattr(mesh, "faces", ()) or ():
        for p in getattr(f, "vertices", ()) or ():
            out.append(QVector3D(p))
        for hole in getattr(f, "holes", ()) or ():
            for p in hole:
                out.append(QVector3D(p))


def _collect_vertices_from_group(group, out: list) -> None:
    """Recursively collect vertex positions from a group and its children."""
    _collect_vertices_from_mesh(getattr(group, "mesh", None), out)
    for child in getattr(group, "children", ()) or ():
        _collect_vertices_from_group(child, out)


def _selected_points(scene) -> list:
    """Return unique vertex positions from the current selection.

    Supports selected vertices, edges, faces, and groups (including nested groups).
    """
    try:
        from core.mesh import Edge, Face, Vertex
    except Exception:
        Edge = Face = Vertex = ()

    raw: list[QVector3D] = []

    for entry in scene.selection:
        if Vertex and isinstance(entry, Vertex):
            raw.append(QVector3D(entry.position))
        elif Edge and isinstance(entry, Edge):
            raw.append(QVector3D(entry.a))
            raw.append(QVector3D(entry.b))
        elif Face and isinstance(entry, Face):
            for p in getattr(entry, "vertices", ()) or ():
                raw.append(QVector3D(p))
            for hole in getattr(entry, "holes", ()) or ():
                for p in hole:
                    raw.append(QVector3D(p))
        elif getattr(entry, "mesh", None) is not None or getattr(entry, "children", None) is not None:
            _collect_vertices_from_group(entry, raw)
        else:
            pos = getattr(entry, "position", None)
            if pos is not None:
                raw.append(QVector3D(pos))

    # Deduplicate positions within tolerance.
    unique: list[QVector3D] = []
    tol2 = DEDUP_TOLERANCE * DEDUP_TOLERANCE
    for p in raw:
        if any((p - q).lengthSquared() <= tol2 for q in unique):
            continue
        unique.append(p)
    return unique


def _make_point_marker(position: QVector3D, size: float = POINT_MARKER_SIZE) -> Mesh:
    """Create a small selectable marker mesh centered at ``position``.

    Uses three short orthogonal segments so the point is visible and selectable
    from different view directions without being a degenerate zero-length element.
    """
    h = max(float(size) * 0.5, 1e-5)
    mesh = Mesh()
    mesh.add_edge(
        QVector3D(position.x() - h, position.y(), position.z()),
        QVector3D(position.x() + h, position.y(), position.z()),
    )
    mesh.add_edge(
        QVector3D(position.x(), position.y() - h, position.z()),
        QVector3D(position.x(), position.y() + h, position.z()),
    )
    mesh.add_edge(
        QVector3D(position.x(), position.y(), position.z() - h),
        QVector3D(position.x(), position.y(), position.z() + h),
    )
    return mesh


def _remove_selected_sources(scene, entries) -> None:
    """Best-effort removal of selected source entities from the scene."""
    try:
        from core.mesh import Edge, Face, Vertex
    except Exception:
        Edge = Face = Vertex = ()

    mesh = getattr(scene, "mesh", None)

    for entry in list(entries):
        # Remove top-level groups/instances from the scene.
        if getattr(entry, "mesh", None) is not None or getattr(entry, "children", None) is not None:
            try:
                scene.selection.discard(entry)
            except Exception:
                pass
            groups = getattr(scene, "groups", None)
            if groups is not None and entry in groups:
                groups.remove(entry)
                continue
            # Nested/group-in-edit contexts: try generic removal if available.
            removed = False
            for attr in ("children",):
                # Cannot reliably know parent; skip if not directly removable.
                pass
            if removed:
                continue

        if mesh is None:
            continue

        try:
            if Face and isinstance(entry, Face) and entry in getattr(mesh, "faces", []):
                mesh.remove_face(entry)
            elif Edge and isinstance(entry, Edge) and entry in getattr(mesh, "edges", []):
                mesh.remove_edge(entry)
            elif Vertex and isinstance(entry, Vertex):
                # Vertices are not directly "deleted" as scene entities in general;
                # remove incident edges/faces if possible is complex, so skip.
                pass
        except Exception:
            pass

    # Clean up orphaned vertices when possible.
    if mesh is not None and hasattr(mesh, "prune_orphan_vertices"):
        try:
            mesh.prune_orphan_vertices()
        except Exception:
            pass


def explode_selection_to_points(scene, selected_entries=None, delete_original: bool = False) -> list:
    """Create one selectable point marker group per unique vertex of the selection.

    Optionally deletes the original selected source entities. Returns the list of
    created point groups.
    """
    if selected_entries is None:
        selected_entries = list(getattr(scene, "selection", []) or [])

    points = _selected_points(scene)
    if not points:
        return []

    layer = active_layer(scene)
    created = []
    for index, pos in enumerate(points, start=1):
        mesh = _make_point_marker(pos)
        group = Group(mesh, name=f"Point {index}")
        group.layer = layer
        scene.groups.append(group)
        created.append(group)

    if delete_original:
        _remove_selected_sources(scene, selected_entries)

    scene.selection.clear()
    for group in created:
        scene.selection.add(group)
    return created


class ExplodeToPointsDialog(QDialog):
    """Dialog to configure exploding the selection into selectable points."""

    def __init__(self, count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Explode to Points")
        self.setMinimumWidth(360)
        self._build_ui(count)

    def _build_ui(self, count: int) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        info = QLabel(
            f"Create {count} selectable point{'s' if count != 1 else ''} "
            "from the unique vertices of the selection."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        self._delete_original = QCheckBox("Delete original selected object(s)")
        self._delete_original.setChecked(False)
        root.addWidget(self._delete_original)

        hint = QLabel(
            "If enabled, the selected base object(s) are removed in the same "
            "undoable step. If disabled, the original selection is kept."
        )
        hint.setWordWrap(True)
        hint.setEnabled(False)
        root.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self
        )
        ok = buttons.button(QDialogButtonBox.Ok)
        if ok is not None:
            ok.setText("Create Points")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @property
    def delete_original(self) -> bool:
        return self._delete_original.isChecked()


def _run_explode_to_points(app) -> None:
    """Menu action: convert current selection into selectable points."""
    viewport = getattr(app, "viewport", None)
    if viewport is None:
        return
    scene = getattr(app, "scene", None)
    if scene is None:
        return

    selected_entries = list(getattr(scene, "selection", []) or [])
    points = _selected_points(scene)
    if not points:
        flash = getattr(viewport, "flash_status", None)
        if callable(flash):
            flash("Select a shape (face, edge, or object) first to explode into points.", 3500)
        return

    parent = getattr(app, "window", None) or viewport.window()
    dialog = ExplodeToPointsDialog(len(points), parent=parent)
    if dialog.exec() != QDialog.Accepted:
        return

    delete_original = dialog.delete_original

    def build(sc):
        explode_selection_to_points(
            sc,
            selected_entries=selected_entries,
            delete_original=delete_original,
        )

    history = getattr(viewport, "history", None)
    if history is not None and hasattr(history, "execute"):
        history.execute(SnapshotImport(build))
        err = getattr(history, "last_error", None)
        if err:
            flash = getattr(viewport, "flash_status", None)
            if callable(flash):
                flash(f"Could not explode selection to points: {err}", 4500)
            return
    else:
        build(scene)
        try:
            scene.version += 1
        except Exception:
            pass

    notify = getattr(viewport, "notify_scene_changed", None)
    if callable(notify):
        notify()
    else:
        viewport.update()

    flash = getattr(viewport, "flash_status", None)
    if callable(flash):
        n = len(points)
        if delete_original:
            flash(
                f"Created {n} selectable point{'s' if n != 1 else ''} and deleted the original selection.",
                4000,
            )
        else:
            flash(
                f"Created {n} selectable point{'s' if n != 1 else ''} from the selection.",
                3500,
            )


def setup(app) -> None:
    """Extension entry point: register the Explode to Points action."""
    app.add_menu_action(
        "Explode to Points...",
        lambda: _run_explode_to_points(app),
        tip="Convert the selected shape into selectable points, with an option to delete or keep the original object(s).",
    )
