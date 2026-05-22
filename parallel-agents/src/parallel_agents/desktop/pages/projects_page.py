from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from parallel_agents.desktop._qt import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    Qt,
    Signal,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService
from parallel_agents.desktop.services.history import HistoryStore


class ProjectsPage(Page):
    project_opened = Signal(object)

    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Projects",
            subtitle="Open an existing project folder or initialize a new local office workspace.",
        )
        self.engine = engine
        self.history = HistoryStore()
        self._trend_cache = []

        actions = QHBoxLayout()
        open_btn = QPushButton("Open Project Folder...")
        open_btn.setObjectName("Primary")
        open_btn.clicked.connect(self._open_project)

        new_btn = QPushButton("Initialize New Office...")
        new_btn.clicked.connect(self._init_project)

        actions.addWidget(open_btn)
        actions.addWidget(new_btn)
        actions.addStretch(1)
        self.body_layout.addLayout(actions)

        self.current_card = QFrame()
        self.current_card.setObjectName("Card")
        card_layout = QVBoxLayout(self.current_card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        self.current_label = QLabel("No project selected.")
        self.current_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.current_meta = QLabel("")
        self.current_meta.setStyleSheet("color: #8a90a2;")
        self.current_stats = QLabel("")
        self.current_stats.setStyleSheet("color: #8a90a2;")
        card_layout.addWidget(self.current_label)
        card_layout.addWidget(self.current_meta)
        card_layout.addWidget(self.current_stats)
        self.body_layout.addWidget(self.current_card)

        self.productivity_card = QFrame()
        self.productivity_card.setObjectName("Card")
        productivity_layout = QVBoxLayout(self.productivity_card)
        productivity_layout.setContentsMargins(20, 16, 20, 16)
        self.productivity_label = QLabel("Release & Productivity")
        self.productivity_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.productivity_meta = QLabel("No evaluation artifacts detected yet.")
        self.productivity_meta.setStyleSheet("color: #8a90a2;")
        self.productivity_stats = QLabel("")
        self.productivity_stats.setStyleSheet("color: #8a90a2;")
        self.productivity_stats.setWordWrap(True)
        self.productivity_trend_label = QLabel("Recent Metric History")
        self.productivity_trend_label.setStyleSheet("font-weight: 600; padding-top: 8px;")
        self.productivity_trend_meta = QLabel("")
        self.productivity_trend_meta.setStyleSheet("color: #8a90a2;")

        trend_controls = QHBoxLayout()
        self.trend_mode = QComboBox()
        self.trend_mode.addItems(["Overall", "Project", "Workflow"])
        self.trend_mode.currentTextChanged.connect(self._on_trend_controls_changed)
        self.trend_metric = QComboBox()
        self.trend_metric.currentTextChanged.connect(self._on_trend_controls_changed)
        self.trend_key = QComboBox()
        self.trend_key.currentTextChanged.connect(self._on_trend_controls_changed)
        self.trend_window = QComboBox()
        self.trend_window.addItems(["All", "7d", "30d", "90d"])
        self.trend_window.currentTextChanged.connect(self._on_trend_controls_changed)
        trend_controls.addWidget(QLabel("Slice"))
        trend_controls.addWidget(self.trend_mode)
        trend_controls.addWidget(QLabel("Metric"))
        trend_controls.addWidget(self.trend_metric, stretch=1)
        trend_controls.addWidget(QLabel("Key"))
        trend_controls.addWidget(self.trend_key, stretch=1)
        trend_controls.addWidget(QLabel("Window"))
        trend_controls.addWidget(self.trend_window)

        self.trend_chart = QTextBrowser()
        self.trend_chart.setOpenExternalLinks(False)
        self.trend_chart.setMinimumHeight(140)

        self.productivity_trend_list = QListWidget()
        productivity_layout.addWidget(self.productivity_label)
        productivity_layout.addWidget(self.productivity_meta)
        productivity_layout.addWidget(self.productivity_stats)
        productivity_layout.addWidget(self.productivity_trend_label)
        productivity_layout.addWidget(self.productivity_trend_meta)
        productivity_layout.addLayout(trend_controls)
        productivity_layout.addWidget(self.trend_chart)
        productivity_layout.addWidget(self.productivity_trend_list)
        self.body_layout.addWidget(self.productivity_card)

        recent_projects_title = QLabel("Recent Project Folders")
        recent_projects_title.setStyleSheet("font-weight: 600; padding-top: 8px;")
        self.body_layout.addWidget(recent_projects_title)

        recent_project_actions = QHBoxLayout()
        open_recent_btn = QPushButton("Open Selected Recent")
        open_recent_btn.clicked.connect(self._open_selected_recent)
        clear_recent_btn = QPushButton("Clear Recent")
        clear_recent_btn.clicked.connect(self._clear_recent_projects)
        recent_project_actions.addWidget(open_recent_btn)
        recent_project_actions.addWidget(clear_recent_btn)
        recent_project_actions.addStretch(1)
        self.body_layout.addLayout(recent_project_actions)

        self.recent_projects_list = QListWidget()
        self.recent_projects_list.itemDoubleClicked.connect(
            lambda _item: self._open_selected_recent()
        )
        self.body_layout.addWidget(self.recent_projects_list)

        self.recent_label = QLabel("Recent Runs")
        self.recent_label.setStyleSheet("font-weight: 600; padding-top: 8px;")
        self.body_layout.addWidget(self.recent_label)

        self.recent_list = QListWidget()
        self.body_layout.addWidget(self.recent_list, stretch=1)
        self._refresh_recent_projects()

    def _open_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select project folder")
        if not path:
            return
        info = self.engine.open_project(path)
        self._refresh(info)

    def _init_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder for new office")
        if not path:
            return
        name, ok = QInputDialog.getText(
            self, "Project name", "Project name:", text=Path(path).name
        )
        if not ok:
            return
        try:
            info = self.engine.init_project(path, name=name or None)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Init failed", str(exc))
            return
        self._refresh(info)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._refresh_recent_projects()
        current = self.engine.current_project()
        if current is not None:
            self._refresh(current)

    def _open_selected_recent(self) -> None:
        item = self.recent_projects_list.currentItem()
        if item is None:
            QMessageBox.information(
                self, "Recent projects", "Select a recent project first."
            )
            return
        root_text = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not root_text:
            return
        root = Path(root_text)
        if not root.exists():
            QMessageBox.warning(self, "Missing folder", f"Path no longer exists:\n{root}")
            return
        info = self.engine.open_project(root)
        self._refresh(info)

    def _clear_recent_projects(self) -> None:
        self.history.clear("project_root")
        self._refresh_recent_projects()

    def _refresh(self, info) -> None:
        self.history.add("project_root", str(info.root), limit=12)
        self._refresh_recent_projects()
        self.current_label.setText(info.name)
        home = self.engine.workspace_home()
        self.current_meta.setText(f"{info.root}\nOffice: {info.office_dir}")
        self.current_stats.setText(
            "Runs: "
            f"{home.run_count}  |  Artifacts: {home.artifact_count}  |  Pending approvals: {home.pending_approval_count}"
            + (f"  |  Branch: {home.current_branch}" if home.current_branch else "")
        )
        self._refresh_productivity()
        self.recent_list.clear()
        for run in self.engine.list_runs():
            item = QListWidgetItem(f"{run['id']}   {run.get('created_at', '')}")
            item.setData(Qt.ItemDataRole.UserRole, run["id"])
            self.recent_list.addItem(item)
        self.project_opened.emit(info)

    def _refresh_productivity(self) -> None:
        snapshot = self.engine.productivity_snapshot()
        trend = self.engine.productivity_trend(limit=8)
        self._trend_cache = trend
        self.productivity_trend_list.clear()
        source_bits: list[str] = []
        if snapshot.score_path is not None:
            source_bits.append(f"score: {snapshot.score_path.name}")
        if snapshot.gate_path is not None:
            source_bits.append(f"gate: {snapshot.gate_path.name}")
        if snapshot.breakdown_path is not None:
            source_bits.append(f"breakdown: {snapshot.breakdown_path.name}")

        if not source_bits:
            self.productivity_meta.setText(
                "No eval artifacts found in .parallel-agents/metrics or eval/."
            )
            self.productivity_stats.setText(
                "Run `parallel-agents eval score` (and optionally `eval breakdown`, `eval gate`) to populate this view."
            )
            self.productivity_trend_meta.setText("")
            self.trend_chart.setPlainText("")
            return

        generated = snapshot.generated_at or "unknown time"
        self.productivity_meta.setText(
            f"Generated: {generated}  |  Sources: {', '.join(source_bits)}"
        )

        lines = [
            f"Impact: {_pct(snapshot.weighted_delivery_impact_score)}",
            f"Acceptance: {_pct(snapshot.acceptance_rate)}",
            f"Regression: {_pct(snapshot.regression_rate)}",
            f"Precision: {_pct(snapshot.finding_precision)}",
            f"Cases: {_num(snapshot.case_count)} (completed {_num(snapshot.completed_count)}, failed {_num(snapshot.failed_count)})",
            f"Cost: {_usd(snapshot.total_cost_usd)}  |  Duration: {_duration(snapshot.total_duration_seconds)}",
        ]
        if snapshot.gate_passed is not None:
            gate_status = "passed" if snapshot.gate_passed else "failed"
            lines.append(f"Release gate: {gate_status}")
            if snapshot.gate_failed_rules:
                lines.append(f"Gate rules: {'; '.join(snapshot.gate_failed_rules)}")
        if snapshot.top_project:
            lines.append(f"Top project bucket: {snapshot.top_project}")
        if snapshot.top_workflow:
            lines.append(f"Top workflow bucket: {snapshot.top_workflow}")
        if snapshot.notes:
            lines.append(f"Notes: {'; '.join(snapshot.notes)}")

        if len(trend) >= 2:
            latest = trend[0]
            previous = trend[1]
            lines.append(
                "Delta vs previous: "
                f"impact {_delta_pct(latest.weighted_delivery_impact_score, previous.weighted_delivery_impact_score)}, "
                f"acceptance {_delta_pct(latest.acceptance_rate, previous.acceptance_rate)}, "
                f"regression {_delta_pct(latest.regression_rate, previous.regression_rate)}"
            )
        self.productivity_stats.setText("\n".join(lines))

        if not trend:
            self.productivity_trend_meta.setText("No historical score artifacts found.")
            self.trend_chart.setPlainText("")
            return
        self.productivity_trend_meta.setText(f"{len(trend)} score snapshots")
        self._sync_trend_controls(trend)
        self._render_trend_chart(trend)
        for entry in trend:
            gate_text = "gate n/a"
            if entry.gate_passed is True:
                gate_text = "gate pass"
            elif entry.gate_passed is False:
                gate_text = "gate fail"
            text = (
                f"{entry.generated_at}  |  impact {_pct(entry.weighted_delivery_impact_score)}  "
                f"|  acceptance {_pct(entry.acceptance_rate)}  "
                f"|  regression {_pct(entry.regression_rate)}  "
                f"|  {gate_text}  "
                f"|  {entry.score_path.name}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, str(entry.score_path))
            self.productivity_trend_list.addItem(item)

    def _on_trend_controls_changed(self, _value: str) -> None:
        if not self._trend_cache:
            return
        self._sync_trend_controls(self._trend_cache, preserve=True)
        self._render_trend_chart(self._trend_cache)

    def _sync_trend_controls(self, trend: list, *, preserve: bool = False) -> None:
        mode = self.trend_mode.currentText()
        mode_metrics = {
            "Overall": [
                "impact",
                "acceptance",
                "regression",
                "precision",
                "cost",
                "duration",
                "cases",
                "failed",
            ],
            "Project": ["cost", "duration", "cases", "failed"],
            "Workflow": ["cost", "duration", "cases", "failed"],
        }
        keys = ["(all)"]
        if mode == "Project":
            keys.extend(sorted({k for point in trend for k in point.project_buckets}))
        elif mode == "Workflow":
            keys.extend(sorted({k for point in trend for k in point.workflow_buckets}))

        current_metric = self.trend_metric.currentText() if preserve else ""
        current_key = self.trend_key.currentText() if preserve else ""

        self.trend_metric.blockSignals(True)
        self.trend_metric.clear()
        self.trend_metric.addItems(mode_metrics.get(mode, mode_metrics["Overall"]))
        if current_metric:
            idx = self.trend_metric.findText(current_metric)
            if idx >= 0:
                self.trend_metric.setCurrentIndex(idx)
        self.trend_metric.blockSignals(False)

        self.trend_key.blockSignals(True)
        self.trend_key.clear()
        self.trend_key.addItems(keys)
        if current_key:
            idx = self.trend_key.findText(current_key)
            if idx >= 0:
                self.trend_key.setCurrentIndex(idx)
        self.trend_key.blockSignals(False)

    def _render_trend_chart(self, trend: list) -> None:
        mode = self.trend_mode.currentText()
        metric = self.trend_metric.currentText().strip() or "impact"
        key = self.trend_key.currentText().strip() or "(all)"
        window_label = self.trend_window.currentText().strip() or "All"

        filtered = _filter_trend_window(trend, window_label)
        if not filtered:
            self.trend_chart.setPlainText("No trend points in selected window.")
            return
        filtered = sorted(filtered, key=lambda point: point.generated_at)
        values = [_trend_value(point, mode, metric, key) for point in filtered]
        present_values = [v for v in values if v is not None]
        spark = _sparkline(present_values)
        latest_value = values[-1] if values else None
        prev_value = values[-2] if len(values) > 1 else None
        delta = _delta_pct(latest_value, prev_value)
        chart_lines = [
            f"{mode} / {metric} / {key} / {window_label}",
            f"Trend: {spark if spark else '(n/a)'}",
            f"Latest: {_metric_value_text(latest_value, metric)}",
            f"Delta vs previous: {delta}",
            "",
            "Points (oldest -> newest):",
        ]
        for point, value in zip(filtered, values):
            chart_lines.append(
                f"- {point.generated_at}: {_metric_value_text(value, metric)}"
            )
        self.trend_chart.setPlainText("\n".join(chart_lines))

    def _refresh_recent_projects(self) -> None:
        self.recent_projects_list.clear()
        roots = self.history.get("project_root", limit=12)
        if not roots:
            placeholder = QListWidgetItem("No recent projects yet")
            placeholder.setFlags(placeholder.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.recent_projects_list.addItem(placeholder)
            return
        for raw in roots:
            root = Path(raw)
            exists = root.exists()
            label = str(root) if exists else f"{root}  [missing]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(root))
            if not exists:
                item.setForeground(self.palette().mid())
            self.recent_projects_list.addItem(item)


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def _usd(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"${value:.4f}"


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60.0
    return f"{minutes:.1f}m"


def _num(value: int | None) -> str:
    if value is None:
        return "n/a"
    return str(value)


def _delta_pct(current: float | None, previous: float | None) -> str:
    if current is None or previous is None:
        return "n/a"
    delta = (current - previous) * 100.0
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.2f}%"


def _filter_trend_window(trend: list, window_label: str) -> list:
    if window_label == "All":
        return list(trend)
    now = datetime.now(timezone.utc)
    days_map = {"7d": 7, "30d": 30, "90d": 90}
    days = days_map.get(window_label)
    if days is None:
        return list(trend)
    min_ts = now - timedelta(days=days)
    output = []
    for point in trend:
        ts = _parse_iso(point.generated_at)
        if ts is not None and ts >= min_ts:
            output.append(point)
    return output


def _parse_iso(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _trend_value(point, mode: str, metric: str, key: str) -> float | None:
    if mode == "Overall":
        if metric == "impact":
            return point.weighted_delivery_impact_score
        if metric == "acceptance":
            return point.acceptance_rate
        if metric == "regression":
            return point.regression_rate
        if metric == "precision":
            return point.finding_precision
        if metric == "cost":
            return point.total_cost_usd
        if metric == "duration":
            return point.total_duration_seconds
        if metric == "cases":
            return float(point.case_count)
        if metric == "failed":
            return float(point.failed_count)
        return None

    bucket_map = point.project_buckets if mode == "Project" else point.workflow_buckets
    if key == "(all)":
        buckets = list(bucket_map.values())
    else:
        single = bucket_map.get(key)
        buckets = [single] if single is not None else []
    if not buckets:
        return None
    if metric == "cost":
        return sum(bucket.total_cost_usd for bucket in buckets)
    if metric == "duration":
        return sum(bucket.total_duration_seconds for bucket in buckets)
    if metric == "cases":
        return float(sum(bucket.case_count for bucket in buckets))
    if metric == "failed":
        return float(sum(bucket.failed_count for bucket in buckets))
    return None


def _metric_value_text(value: float | None, metric: str) -> str:
    if value is None:
        return "n/a"
    if metric in {"impact", "acceptance", "regression", "precision"}:
        return f"{value * 100:.2f}%"
    if metric == "cost":
        return f"${value:.4f}"
    if metric == "duration":
        if value < 60:
            return f"{value:.1f}s"
        return f"{value / 60.0:.1f}m"
    if metric in {"cases", "failed"}:
        return str(int(round(value)))
    return f"{value:.4f}"


def _sparkline(values: list[float]) -> str:
    if not values:
        return ""
    chars = "._-:=+*#"
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return chars[0] * len(values)
    pieces = []
    for value in values:
        ratio = (value - min_v) / (max_v - min_v)
        idx = int(round(ratio * (len(chars) - 1)))
        pieces.append(chars[idx])
    return "".join(pieces)
