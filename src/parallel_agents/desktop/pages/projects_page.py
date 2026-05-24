from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from parallel_agents.desktop._qt import (
    QColor,
    QComboBox,
    QFileDialog,
    QFont,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPainter,
    QPen,
    QPixmap,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    Qt,
    Signal,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService, ProductivityComparison
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
        self._current_comparison: ProductivityComparison | None = None

        actions = QHBoxLayout()
        open_btn = QPushButton("Open Project Folder...")
        open_btn.setObjectName("Primary")
        open_btn.clicked.connect(self._open_project)

        new_btn = QPushButton("Initialize New Office...")
        new_btn.clicked.connect(self._init_project)
        self.doctor_btn = QPushButton("Run Doctor")
        self.doctor_btn.clicked.connect(self._run_doctor)
        self.fix_setup_btn = QPushButton("Fix Setup")
        self.fix_setup_btn.clicked.connect(self._fix_setup)
        self.fix_setup_btn.setEnabled(False)

        actions.addWidget(open_btn)
        actions.addWidget(new_btn)
        actions.addWidget(self.doctor_btn)
        actions.addWidget(self.fix_setup_btn)
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
        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.clicked.connect(self._export_trend_csv)
        self.export_md_btn = QPushButton("Export Report")
        self.export_md_btn.clicked.connect(self._export_trend_markdown)
        self.export_png_btn = QPushButton("Export Chart")
        self.export_png_btn.clicked.connect(self._export_trend_image)
        trend_controls.addWidget(QLabel("Slice"))
        trend_controls.addWidget(self.trend_mode)
        trend_controls.addWidget(QLabel("Metric"))
        trend_controls.addWidget(self.trend_metric, stretch=1)
        trend_controls.addWidget(QLabel("Key"))
        trend_controls.addWidget(self.trend_key, stretch=1)
        trend_controls.addWidget(QLabel("Window"))
        trend_controls.addWidget(self.trend_window)
        trend_controls.addWidget(self.export_csv_btn)
        trend_controls.addWidget(self.export_md_btn)
        trend_controls.addWidget(self.export_png_btn)

        self.trend_visual = QLabel()
        self.trend_visual.setMinimumHeight(220)
        self.trend_visual.setObjectName("Card")
        self.trend_visual.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.trend_chart = QTextBrowser()
        self.trend_chart.setOpenExternalLinks(False)
        self.trend_chart.setMinimumHeight(140)

        self.productivity_trend_list = QListWidget()
        compare_controls = QHBoxLayout()
        self.compare_baseline = QComboBox()
        self.compare_candidate = QComboBox()
        self.compare_btn = QPushButton("Compare")
        self.compare_btn.clicked.connect(self._render_comparison)
        self.export_compare_btn = QPushButton("Export Compare")
        self.export_compare_btn.clicked.connect(self._export_comparison_report)
        compare_controls.addWidget(QLabel("Baseline"))
        compare_controls.addWidget(self.compare_baseline, stretch=1)
        compare_controls.addWidget(QLabel("Candidate"))
        compare_controls.addWidget(self.compare_candidate, stretch=1)
        compare_controls.addWidget(self.compare_btn)
        compare_controls.addWidget(self.export_compare_btn)
        self.compare_view = QTextBrowser()
        self.compare_view.setMinimumHeight(120)
        self.compare_view.setOpenExternalLinks(False)
        self.compare_case_list = QListWidget()
        self.compare_case_list.itemSelectionChanged.connect(self._show_selected_case_evidence)
        self.compare_case_evidence = QTextBrowser()
        self.compare_case_evidence.setOpenExternalLinks(True)
        self.compare_case_evidence.setMinimumHeight(120)

        productivity_layout.addWidget(self.productivity_label)
        productivity_layout.addWidget(self.productivity_meta)
        productivity_layout.addWidget(self.productivity_stats)
        productivity_layout.addWidget(self.productivity_trend_label)
        productivity_layout.addWidget(self.productivity_trend_meta)
        productivity_layout.addLayout(trend_controls)
        productivity_layout.addWidget(self.trend_visual)
        productivity_layout.addWidget(self.trend_chart)
        productivity_layout.addWidget(self.productivity_trend_list)
        productivity_layout.addLayout(compare_controls)
        productivity_layout.addWidget(self.compare_view)
        productivity_layout.addWidget(QLabel("Case-Level Evidence Links"))
        productivity_layout.addWidget(self.compare_case_list)
        productivity_layout.addWidget(self.compare_case_evidence)
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

    def _run_doctor(self) -> None:
        current = self.engine.current_project()
        if current is None:
            QMessageBox.information(self, "Office Doctor", "Open a project first.")
            return
        diagnostics = self.engine.office_diagnostics()
        checks = diagnostics.get("checks", [])
        summary_lines = [
            f"Passed: {diagnostics.get('passed_checks', 0)}",
            f"Warnings: {diagnostics.get('warning_checks', 0)}",
            f"Failures: {diagnostics.get('failed_checks', 0)}",
        ]
        detail_lines: list[str] = []
        for item in checks:
            if not isinstance(item, dict):
                continue
            detail_lines.append(
                f"- {item.get('name', '-')}: {item.get('status', 'unknown')} ({item.get('detail', '')})"
            )
        message = QMessageBox(self)
        message.setWindowTitle("Office Doctor")
        message.setText("Project diagnostics complete.")
        message.setInformativeText("\n".join(summary_lines))
        message.setDetailedText("\n".join(detail_lines) if detail_lines else "No checks available.")
        message.exec()
        self._refresh(current)

    def _fix_setup(self) -> None:
        current = self.engine.current_project()
        if current is None:
            QMessageBox.information(self, "Fix Setup", "Open a project first.")
            return
        result = self.engine.fix_office_setup()
        actions = result.actions_taken or ["none"]
        message_lines = [
            f"Actions taken: {', '.join(actions)}",
            f"After -> passed: {result.after.get('passed_checks', 0)}, "
            f"warnings: {result.after.get('warning_checks', 0)}, "
            f"failures: {result.after.get('failed_checks', 0)}",
        ]
        details = []
        if result.suggested_commands:
            details.append("Suggested commands:")
            details.extend(f"- {command}" for command in result.suggested_commands)
        else:
            details.append("No additional commands suggested.")
        message = QMessageBox(self)
        message.setWindowTitle("Fix Setup")
        message.setText("Setup remediation complete.")
        message.setInformativeText("\n".join(message_lines))
        message.setDetailedText("\n".join(details))
        message.exec()
        self._refresh(current)

    def _clear_recent_projects(self) -> None:
        self.history.clear("project_root")
        self._refresh_recent_projects()

    def _refresh(self, info) -> None:
        self.history.add("project_root", str(info.root), limit=12)
        self._refresh_recent_projects()
        self.current_label.setText(info.name)
        home = self.engine.workspace_home()
        self.current_meta.setText(f"{info.root}\nOffice: {info.office_dir}")
        doctor_status = "healthy" if home.diagnostics_healthy else "attention"
        self.current_stats.setText(
            "Runs: "
            f"{home.run_count}  |  Artifacts: {home.artifact_count}  |  Pending approvals: {home.pending_approval_count}"
            f"  |  Doctor: {doctor_status} ({home.diagnostics_failures} fail, {home.diagnostics_warnings} warn)"
            + (f"  |  Branch: {home.current_branch}" if home.current_branch else "")
        )
        self.fix_setup_btn.setEnabled(not home.diagnostics_healthy)
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
            self.trend_visual.setPixmap(_build_empty_trend_pixmap("No trend data"))
            self.compare_view.setPlainText("")
            self.compare_case_list.clear()
            self.compare_case_evidence.setPlainText("")
            self._current_comparison = None
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
            self.trend_visual.setPixmap(_build_empty_trend_pixmap("No score snapshots"))
            self.compare_view.setPlainText("")
            self.compare_case_list.clear()
            self.compare_case_evidence.setPlainText("")
            self._current_comparison = None
            return
        self.productivity_trend_meta.setText(f"{len(trend)} score snapshots")
        self._sync_trend_controls(trend)
        self._render_trend_chart(trend)
        self._sync_compare_controls(trend)
        self._render_comparison()
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
        ctx = self._trend_context(trend)
        filtered = ctx["filtered"]
        if not filtered:
            self.trend_chart.setPlainText("No trend points in selected window.")
            self.trend_visual.setPixmap(_build_empty_trend_pixmap("No points in selected window"))
            return
        mode = ctx["mode"]
        metric = ctx["metric"]
        key = ctx["key"]
        window_label = ctx["window"]
        values = ctx["values"]
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
        pixmap = _build_trend_pixmap(
            values=values,
            metric=metric,
            title=f"{mode} / {metric} / {key} / {window_label}",
            width=max(760, self.trend_visual.width()),
            height=max(220, self.trend_visual.height()),
        )
        self.trend_visual.setPixmap(pixmap)

    def _trend_context(self, trend: list) -> dict:
        mode = self.trend_mode.currentText()
        metric = self.trend_metric.currentText().strip() or "impact"
        key = self.trend_key.currentText().strip() or "(all)"
        window_label = self.trend_window.currentText().strip() or "All"
        filtered = _filter_trend_window(trend, window_label)
        filtered = sorted(filtered, key=lambda point: point.generated_at)
        values = [_trend_value(point, mode, metric, key) for point in filtered]
        return {
            "mode": mode,
            "metric": metric,
            "key": key,
            "window": window_label,
            "filtered": filtered,
            "values": values,
        }

    def _export_trend_csv(self) -> None:
        if not self._trend_cache:
            QMessageBox.information(self, "Export trend", "No trend data to export.")
            return
        ctx = self._trend_context(self._trend_cache)
        if not ctx["filtered"]:
            QMessageBox.information(
                self,
                "Export trend",
                "No trend points in the selected window.",
            )
            return
        project = self.engine.current_project()
        default_dir = str((project.office_dir / "metrics").resolve()) if project else "."
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        default_path = str(
            Path(default_dir) / f"desktop-trend-{ctx['mode'].lower()}-{ctx['metric']}-{timestamp}.csv"
        )
        selected, _filter_name = QFileDialog.getSaveFileName(
            self,
            "Export Trend CSV",
            default_path,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not selected:
            return
        path = Path(selected)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "generated_at",
                    "slice_mode",
                    "metric",
                    "slice_key",
                    "window",
                    "value_raw",
                    "value_display",
                    "gate_status",
                    "score_path",
                ]
            )
            for point, value in zip(ctx["filtered"], ctx["values"]):
                gate_status = "n/a"
                if point.gate_passed is True:
                    gate_status = "pass"
                elif point.gate_passed is False:
                    gate_status = "fail"
                writer.writerow(
                    [
                        point.generated_at,
                        ctx["mode"],
                        ctx["metric"],
                        ctx["key"],
                        ctx["window"],
                        "" if value is None else value,
                        _metric_value_text(value, ctx["metric"]),
                        gate_status,
                        str(point.score_path),
                    ]
                )
        QMessageBox.information(self, "Export trend", f"CSV saved:\n{path}")

    def _export_trend_markdown(self) -> None:
        if not self._trend_cache:
            QMessageBox.information(self, "Export report", "No trend data to export.")
            return
        ctx = self._trend_context(self._trend_cache)
        if not ctx["filtered"]:
            QMessageBox.information(
                self,
                "Export report",
                "No trend points in the selected window.",
            )
            return
        project = self.engine.current_project()
        default_dir = str((project.office_dir / "metrics").resolve()) if project else "."
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        default_path = str(
            Path(default_dir) / f"desktop-trend-{ctx['mode'].lower()}-{ctx['metric']}-{timestamp}.md"
        )
        selected, _filter_name = QFileDialog.getSaveFileName(
            self,
            "Export Trend Report",
            default_path,
            "Markdown Files (*.md);;All Files (*)",
        )
        if not selected:
            return
        path = Path(selected)
        path.parent.mkdir(parents=True, exist_ok=True)

        latest_value = ctx["values"][-1] if ctx["values"] else None
        prev_value = ctx["values"][-2] if len(ctx["values"]) > 1 else None
        report_lines = [
            "# Desktop Trend Report",
            "",
            f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
            f"- Slice: {ctx['mode']}",
            f"- Metric: {ctx['metric']}",
            f"- Key: {ctx['key']}",
            f"- Window: {ctx['window']}",
            f"- Points: {len(ctx['filtered'])}",
            f"- Latest: {_metric_value_text(latest_value, ctx['metric'])}",
            f"- Delta vs previous: {_delta_pct(latest_value, prev_value)}",
            "",
            "| Timestamp | Value | Gate | Score File |",
            "|---|---:|---|---|",
        ]
        for point, value in zip(ctx["filtered"], ctx["values"]):
            gate_status = "n/a"
            if point.gate_passed is True:
                gate_status = "pass"
            elif point.gate_passed is False:
                gate_status = "fail"
            report_lines.append(
                "| "
                f"{point.generated_at} | {_metric_value_text(value, ctx['metric'])} | "
                f"{gate_status} | {point.score_path.name} |"
            )
        path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
        QMessageBox.information(self, "Export report", f"Report saved:\n{path}")

    def _export_trend_image(self) -> None:
        if not self._trend_cache:
            QMessageBox.information(self, "Export chart", "No trend data to export.")
            return
        ctx = self._trend_context(self._trend_cache)
        if not ctx["filtered"]:
            QMessageBox.information(
                self,
                "Export chart",
                "No trend points in the selected window.",
            )
            return
        project = self.engine.current_project()
        default_dir = str((project.office_dir / "metrics").resolve()) if project else "."
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        default_path = str(
            Path(default_dir) / f"desktop-trend-{ctx['mode'].lower()}-{ctx['metric']}-{timestamp}.png"
        )
        selected, _filter_name = QFileDialog.getSaveFileName(
            self,
            "Export Trend Chart",
            default_path,
            "PNG Files (*.png);;All Files (*)",
        )
        if not selected:
            return
        path = Path(selected)
        path.parent.mkdir(parents=True, exist_ok=True)
        pixmap = _build_trend_pixmap(
            values=ctx["values"],
            metric=ctx["metric"],
            title=f"{ctx['mode']} / {ctx['metric']} / {ctx['key']} / {ctx['window']}",
            width=max(960, self.trend_visual.width()),
            height=max(260, self.trend_visual.height()),
        )
        if not pixmap.save(str(path), "PNG"):
            QMessageBox.warning(self, "Export chart", f"Failed to save chart:\n{path}")
            return
        QMessageBox.information(self, "Export chart", f"Chart saved:\n{path}")

    def _sync_compare_controls(self, trend: list) -> None:
        previous_baseline = self.compare_baseline.currentData()
        previous_candidate = self.compare_candidate.currentData()

        self.compare_baseline.blockSignals(True)
        self.compare_candidate.blockSignals(True)
        self.compare_baseline.clear()
        self.compare_candidate.clear()
        for point in trend:
            label = (
                f"{point.generated_at} | impact {_pct(point.weighted_delivery_impact_score)} "
                f"| {point.score_path.name}"
            )
            score_path = str(point.score_path)
            self.compare_baseline.addItem(label, score_path)
            self.compare_candidate.addItem(label, score_path)

        if trend:
            baseline_index = 1 if len(trend) > 1 else 0
            candidate_index = 0
            if previous_baseline:
                idx = self.compare_baseline.findData(previous_baseline)
                if idx >= 0:
                    baseline_index = idx
            if previous_candidate:
                idx = self.compare_candidate.findData(previous_candidate)
                if idx >= 0:
                    candidate_index = idx
            self.compare_baseline.setCurrentIndex(baseline_index)
            self.compare_candidate.setCurrentIndex(candidate_index)
        self.compare_baseline.blockSignals(False)
        self.compare_candidate.blockSignals(False)

    def _render_comparison(self) -> None:
        baseline = str(self.compare_baseline.currentData() or "").strip()
        candidate = str(self.compare_candidate.currentData() or "").strip()
        if not baseline or not candidate:
            self.compare_view.setPlainText("Select baseline and candidate snapshots.")
            self.compare_case_list.clear()
            self.compare_case_evidence.setPlainText("")
            self._current_comparison = None
            return
        if baseline == candidate:
            self.compare_view.setPlainText(
                "Baseline and candidate are the same snapshot. Select two different points."
            )
            self.compare_case_list.clear()
            self.compare_case_evidence.setPlainText("")
            self._current_comparison = None
            return
        try:
            comparison = self.engine.compare_productivity_snapshots(
                baseline_score_path=baseline,
                candidate_score_path=candidate,
            )
        except Exception as exc:  # noqa: BLE001
            self.compare_view.setPlainText(f"Comparison failed: {exc}")
            self.compare_case_list.clear()
            self.compare_case_evidence.setPlainText("")
            self._current_comparison = None
            return
        self._current_comparison = comparison
        self.compare_view.setPlainText(_comparison_report_text(comparison))
        self._populate_case_change_list(comparison)

    def _export_comparison_report(self) -> None:
        baseline = str(self.compare_baseline.currentData() or "").strip()
        candidate = str(self.compare_candidate.currentData() or "").strip()
        if not baseline or not candidate or baseline == candidate:
            QMessageBox.information(
                self,
                "Export compare",
                "Pick two different snapshots first.",
            )
            return
        try:
            comparison = self.engine.compare_productivity_snapshots(
                baseline_score_path=baseline,
                candidate_score_path=candidate,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Export compare", f"Comparison failed:\n{exc}")
            return

        project = self.engine.current_project()
        default_dir = str((project.office_dir / "metrics").resolve()) if project else "."
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        default_path = str(Path(default_dir) / f"desktop-compare-{timestamp}.md")
        selected, _filter_name = QFileDialog.getSaveFileName(
            self,
            "Export Comparison Report",
            default_path,
            "Markdown Files (*.md);;All Files (*)",
        )
        if not selected:
            return
        path = Path(selected)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_comparison_report_markdown(comparison), encoding="utf-8")
        QMessageBox.information(self, "Export compare", f"Report saved:\n{path}")

    def _populate_case_change_list(self, comparison: ProductivityComparison) -> None:
        self.compare_case_list.clear()
        if not comparison.case_changes:
            self.compare_case_evidence.setPlainText("No case-level changes found.")
            return
        for change in comparison.case_changes:
            label = (
                f"{change.case_id} | "
                f"{change.baseline_status or 'n/a'} -> {change.candidate_status or 'n/a'} | "
                f"cost {_signed_usd(change.total_cost_usd_delta)} | "
                f"duration {_signed_duration(change.duration_seconds_delta)}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, change.case_id)
            self.compare_case_list.addItem(item)
        self.compare_case_list.setCurrentRow(0)
        self._show_selected_case_evidence()

    def _show_selected_case_evidence(self) -> None:
        comparison = self._current_comparison
        if comparison is None:
            self.compare_case_evidence.setPlainText("")
            return
        item = self.compare_case_list.currentItem()
        if item is None:
            self.compare_case_evidence.setPlainText("Select a case row to inspect evidence links.")
            return
        case_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not case_id:
            self.compare_case_evidence.setPlainText("Select a case row to inspect evidence links.")
            return
        selected = next((c for c in comparison.case_changes if c.case_id == case_id), None)
        if selected is None:
            self.compare_case_evidence.setPlainText("Case change not found.")
            return

        links: list[str] = []
        links.extend(
            _path_markdown_links(
                "Baseline score",
                comparison.baseline_score_path,
                "Candidate score",
                comparison.candidate_score_path,
            )
        )
        links.extend(
            _path_markdown_links(
                "Baseline gate",
                comparison.baseline_gate_path,
                "Candidate gate",
                comparison.candidate_gate_path,
            )
        )
        links.extend(
            _path_markdown_links(
                "Baseline breakdown",
                comparison.baseline_breakdown_path,
                "Candidate breakdown",
                comparison.candidate_breakdown_path,
            )
        )
        links.extend(
            _path_markdown_links(
                "Baseline results",
                comparison.baseline_results_path,
                "Candidate results",
                comparison.candidate_results_path,
            )
        )

        project = self.engine.current_project()
        if project is not None:
            if selected.baseline_run_id:
                baseline_artifact = (
                    project.office_dir
                    / selected.baseline_run_id
                    / "company"
                    / "final-output.json"
                )
                if baseline_artifact.exists():
                    links.append(_to_md_file_link("Baseline run final output", baseline_artifact))
            if selected.candidate_run_id:
                candidate_artifact = (
                    project.office_dir
                    / selected.candidate_run_id
                    / "company"
                    / "final-output.json"
                )
                if candidate_artifact.exists():
                    links.append(_to_md_file_link("Candidate run final output", candidate_artifact))

        if not links:
            links.append("No evidence file links resolved for this case.")

        details = [
            f"### Case `{selected.case_id}`",
            "",
            f"- Status: `{selected.baseline_status or 'n/a'}` -> `{selected.candidate_status or 'n/a'}`",
            f"- Cost delta: `{_signed_usd(selected.total_cost_usd_delta)}`",
            f"- Duration delta: `{_signed_duration(selected.duration_seconds_delta)}`",
            f"- Findings delta: `{_signed_optional_int(selected.findings_count_delta)}`",
            f"- Recommendations delta: `{_signed_optional_int(selected.recommendations_count_delta)}`",
            f"- Patch changed: `{'yes' if selected.patch_generated_changed else 'no'}`",
            "",
            "### Evidence Links",
            "",
            *[f"- {link}" for link in links],
            "",
            "Tip: result files include full per-case evidence payloads by case_id.",
        ]
        self.compare_case_evidence.setMarkdown("\n".join(details))

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


def _build_empty_trend_pixmap(message: str) -> QPixmap:
    pixmap = QPixmap(900, 220)
    pixmap.fill(QColor("#0f141c"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#8a90a2"))
    painter.setFont(QFont("Segoe UI", 12))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, message)
    painter.end()
    return pixmap


def _build_trend_pixmap(
    *,
    values: list[float | None],
    metric: str,
    title: str,
    width: int = 900,
    height: int = 220,
) -> QPixmap:
    w = max(640, int(width))
    h = max(180, int(height))
    pixmap = QPixmap(w, h)
    pixmap.fill(QColor("#0f141c"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    margin_left = 56
    margin_right = 20
    margin_top = 30
    margin_bottom = 34
    plot_w = max(120, w - margin_left - margin_right)
    plot_h = max(80, h - margin_top - margin_bottom)
    x0 = margin_left
    y0 = margin_top
    x1 = x0 + plot_w
    y1 = y0 + plot_h

    painter.setPen(QPen(QColor("#3a4354"), 1))
    for i in range(5):
        y = y0 + int((plot_h * i) / 4)
        painter.drawLine(x0, y, x1, y)

    painter.setPen(QPen(QColor("#5f6a80"), 1))
    painter.drawLine(x0, y1, x1, y1)
    painter.drawLine(x0, y0, x0, y1)

    present = [(idx, val) for idx, val in enumerate(values) if val is not None]
    if not present:
        painter.setPen(QColor("#8a90a2"))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "No values to plot")
        painter.end()
        return pixmap

    raw_vals = [float(val) for _, val in present]
    min_v = min(raw_vals)
    max_v = max(raw_vals)
    if max_v == min_v:
        padding = max(1.0, abs(max_v) * 0.1)
        min_v -= padding
        max_v += padding

    def _x_for_index(index: int) -> int:
        if len(values) <= 1:
            return x0
        return x0 + int((plot_w * index) / (len(values) - 1))

    def _y_for_value(value: float) -> int:
        ratio = (value - min_v) / (max_v - min_v)
        ratio = max(0.0, min(1.0, ratio))
        return y1 - int(plot_h * ratio)

    is_count_metric = metric in {"cases", "failed"}
    if is_count_metric:
        painter.setPen(QPen(QColor("#59a2ff"), 1))
        painter.setBrush(QColor("#2f6fb8"))
        bar_w = max(6, int(plot_w / max(8, len(values) * 2)))
        for idx, val in present:
            x = _x_for_index(idx) - bar_w // 2
            y = _y_for_value(float(val))
            painter.drawRect(x, y, bar_w, y1 - y)
    else:
        painter.setPen(QPen(QColor("#59a2ff"), 2))
        prev_point: tuple[int, int] | None = None
        for idx, val in present:
            x = _x_for_index(idx)
            y = _y_for_value(float(val))
            if prev_point is not None:
                painter.drawLine(prev_point[0], prev_point[1], x, y)
            prev_point = (x, y)
        painter.setPen(QPen(QColor("#a7d0ff"), 1))
        painter.setBrush(QColor("#a7d0ff"))
        for idx, val in present:
            x = _x_for_index(idx)
            y = _y_for_value(float(val))
            painter.drawEllipse(x - 2, y - 2, 4, 4)

    painter.setPen(QColor("#8a90a2"))
    painter.setFont(QFont("Segoe UI", 9))
    painter.drawText(8, y0 + 6, _metric_value_text(max_v, metric))
    painter.drawText(8, y1 + 4, _metric_value_text(min_v, metric))
    painter.drawText(x0, h - 10, "old")
    painter.drawText(x1 - 32, h - 10, "new")

    latest_idx, latest_val = present[-1]
    latest_y = _y_for_value(float(latest_val))
    latest_x = _x_for_index(latest_idx)
    painter.setPen(QPen(QColor("#efcf78"), 1))
    painter.drawLine(latest_x, y0, latest_x, y1)
    painter.setPen(QColor("#efcf78"))
    painter.drawText(
        min(x1 - 180, latest_x + 8),
        max(y0 + 12, latest_y - 8),
        f"latest: {_metric_value_text(float(latest_val), metric)}",
    )

    painter.setPen(QColor("#d6dae5"))
    painter.setFont(QFont("Segoe UI Semibold", 10))
    painter.drawText(10, 18, title)
    painter.end()
    return pixmap


def _comparison_report_text(comparison: ProductivityComparison) -> str:
    lines = [
        f"Baseline: {comparison.baseline_generated_at} ({comparison.baseline_score_path.name})",
        f"Candidate: {comparison.candidate_generated_at} ({comparison.candidate_score_path.name})",
        "",
        f"Impact delta: {_signed_pct(comparison.weighted_delivery_impact_delta)}",
        f"Acceptance delta: {_signed_pct(comparison.acceptance_rate_delta)}",
        f"Regression delta: {_signed_pct(comparison.regression_rate_delta)}",
        f"Precision delta: {_signed_pct(comparison.finding_precision_delta)}",
        f"Completed delta: {_signed_int(comparison.completed_count_delta)}",
        f"Failed delta: {_signed_int(comparison.failed_count_delta)}",
        f"Case count delta: {_signed_int(comparison.case_count_delta)}",
        f"Cost delta: {_signed_usd(comparison.total_cost_usd_delta)}",
        f"Duration delta: {_signed_duration(comparison.total_duration_seconds_delta)}",
        "",
        "Gate baseline/candidate: "
        f"{_gate_text(comparison.baseline_gate_passed)} -> {_gate_text(comparison.candidate_gate_passed)}",
    ]
    if comparison.top_workflow_deltas:
        lines.append("")
        lines.append("Top workflow deltas:")
        for entry in comparison.top_workflow_deltas:
            lines.append(
                "- "
                f"{entry.key}: cases {_signed_int(entry.case_count_delta)}, "
                f"failed {_signed_int(entry.failed_count_delta)}, "
                f"cost {_signed_usd(entry.total_cost_usd_delta)}, "
                f"duration {_signed_duration(entry.total_duration_seconds_delta)}"
            )
    if comparison.top_project_deltas:
        lines.append("")
        lines.append("Top project deltas:")
        for entry in comparison.top_project_deltas:
            lines.append(
                "- "
                f"{entry.key}: cases {_signed_int(entry.case_count_delta)}, "
                f"failed {_signed_int(entry.failed_count_delta)}, "
                f"cost {_signed_usd(entry.total_cost_usd_delta)}, "
                f"duration {_signed_duration(entry.total_duration_seconds_delta)}"
            )
    if comparison.case_changes:
        lines.append("")
        lines.append("Top case changes:")
        for entry in comparison.case_changes:
            lines.append(
                "- "
                f"{entry.case_id}: status {entry.baseline_status or 'n/a'} -> {entry.candidate_status or 'n/a'}, "
                f"cost {_signed_usd(entry.total_cost_usd_delta)}, "
                f"duration {_signed_duration(entry.duration_seconds_delta)}, "
                f"findings {_signed_optional_int(entry.findings_count_delta)}, "
                f"recs {_signed_optional_int(entry.recommendations_count_delta)}, "
                f"patch_changed {'yes' if entry.patch_generated_changed else 'no'}"
            )
    return "\n".join(lines)


def _comparison_report_markdown(comparison: ProductivityComparison) -> str:
    lines = [
        "# Desktop Productivity Comparison",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Baseline: `{comparison.baseline_generated_at}` (`{comparison.baseline_score_path.name}`)",
        f"- Candidate: `{comparison.candidate_generated_at}` (`{comparison.candidate_score_path.name}`)",
        "",
        "| Metric | Delta (Candidate - Baseline) |",
        "|---|---:|",
        f"| Impact | {_signed_pct(comparison.weighted_delivery_impact_delta)} |",
        f"| Acceptance | {_signed_pct(comparison.acceptance_rate_delta)} |",
        f"| Regression | {_signed_pct(comparison.regression_rate_delta)} |",
        f"| Precision | {_signed_pct(comparison.finding_precision_delta)} |",
        f"| Completed | {_signed_int(comparison.completed_count_delta)} |",
        f"| Failed | {_signed_int(comparison.failed_count_delta)} |",
        f"| Case count | {_signed_int(comparison.case_count_delta)} |",
        f"| Cost (USD) | {_signed_usd(comparison.total_cost_usd_delta)} |",
        f"| Duration | {_signed_duration(comparison.total_duration_seconds_delta)} |",
        "",
        "Gate baseline/candidate: "
        f"{_gate_text(comparison.baseline_gate_passed)} -> {_gate_text(comparison.candidate_gate_passed)}",
        "",
    ]
    if comparison.top_workflow_deltas:
        lines.extend(
            [
                "## Workflow Deltas",
                "",
                "| Workflow | Cases | Failed | Cost (USD) | Duration |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for entry in comparison.top_workflow_deltas:
            lines.append(
                "| "
                f"{entry.key} | {_signed_int(entry.case_count_delta)} | {_signed_int(entry.failed_count_delta)} | "
                f"{_signed_usd(entry.total_cost_usd_delta)} | {_signed_duration(entry.total_duration_seconds_delta)} |"
            )
        lines.append("")
    if comparison.top_project_deltas:
        lines.extend(
            [
                "## Project Deltas",
                "",
                "| Project | Cases | Failed | Cost (USD) | Duration |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for entry in comparison.top_project_deltas:
            lines.append(
                "| "
                f"{entry.key} | {_signed_int(entry.case_count_delta)} | {_signed_int(entry.failed_count_delta)} | "
                f"{_signed_usd(entry.total_cost_usd_delta)} | {_signed_duration(entry.total_duration_seconds_delta)} |"
            )
        lines.append("")
    if comparison.case_changes:
        lines.extend(
            [
                "## Case Changes",
                "",
                "| Case | Status | Cost | Duration | Findings | Recs | Patch Changed |",
                "|---|---|---:|---:|---:|---:|---|",
            ]
        )
        for entry in comparison.case_changes:
            status_text = f"{entry.baseline_status or 'n/a'} -> {entry.candidate_status or 'n/a'}"
            lines.append(
                "| "
                f"{entry.case_id} | {status_text} | {_signed_usd(entry.total_cost_usd_delta)} | "
                f"{_signed_duration(entry.duration_seconds_delta)} | "
                f"{_signed_optional_int(entry.findings_count_delta)} | "
                f"{_signed_optional_int(entry.recommendations_count_delta)} | "
                f"{'yes' if entry.patch_generated_changed else 'no'} |"
            )
        lines.append("")
    return "\n".join(lines)


def _signed_pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100:.2f}%"


def _signed_usd(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value >= 0 else ""
    return f"{sign}${abs(value):.4f}" if value < 0 else f"{sign}${value:.4f}"


def _signed_duration(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value >= 0 else "-"
    seconds = abs(value)
    if seconds < 60:
        return f"{sign}{seconds:.1f}s"
    return f"{sign}{(seconds / 60.0):.1f}m"


def _signed_int(value: int) -> str:
    return f"{value:+d}"


def _signed_optional_int(value: int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:+d}"


def _gate_text(value: bool | None) -> str:
    if value is True:
        return "pass"
    if value is False:
        return "fail"
    return "n/a"


def _path_markdown_links(
    left_label: str,
    left_path: Path | None,
    right_label: str,
    right_path: Path | None,
) -> list[str]:
    output: list[str] = []
    if left_path is not None and left_path.exists():
        output.append(_to_md_file_link(left_label, left_path))
    if right_path is not None and right_path.exists():
        output.append(_to_md_file_link(right_label, right_path))
    return output


def _to_md_file_link(label: str, path: Path) -> str:
    try:
        uri = path.resolve().as_uri()
    except ValueError:
        resolved = str(path.resolve()).replace("\\", "/")
        uri = f"file:///{resolved}"
    return f"[{label}]({uri})"


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
