from __future__ import annotations

from pathlib import Path

from parallel_agents.desktop._qt import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    Signal,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService
from parallel_agents.desktop.services.history import HistoryStore
from parallel_agents.desktop.services.workers import AsyncJob


def _editable_combo(items: list[str], placeholder: str) -> QComboBox:
    combo = QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    combo.addItems(items)
    combo.setCurrentText("")
    combo.lineEdit().setPlaceholderText(placeholder)
    return combo


class _StepCard(QFrame):
    def __init__(self, name: str, description: str) -> None:
        super().__init__()
        self.setObjectName("Card")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.title = QLabel(name)
        self.title.setStyleSheet("font-size: 15px; font-weight: 600; color: #f0f2f7;")
        header.addWidget(self.title)
        header.addStretch(1)
        self.status = QLabel("idle")
        self.status.setObjectName("WorkerStatusIdle")
        header.addWidget(self.status)
        outer.addLayout(header)

        self.description = QLabel(description)
        self.description.setStyleSheet("color: #8a90a2; font-size: 13px;")
        self.description.setWordWrap(True)
        outer.addWidget(self.description)

        self.extra_row = QHBoxLayout()
        outer.addLayout(self.extra_row)

        action = QHBoxLayout()
        action.addStretch(1)
        self.button = QPushButton("Generate")
        self.button.setObjectName("Primary")
        action.addWidget(self.button)
        outer.addLayout(action)

    def set_status(self, status: str, style: str) -> None:
        self.status.setText(status)
        self.status.setObjectName(style)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)


class CompanyPage(Page):
    artifact_created = Signal(str, Path)  # run_id, artifact_path

    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Company",
            subtitle="Walk an idea through brief, PR/FAQ, tech stack, RFC, roadmap, sprint, and a gated GitHub apply.",
        )
        self.engine = engine
        self.history = HistoryStore()
        self._job: AsyncJob | None = None
        self._run_id: str | None = None

        # --- scrollable body since the workflow is long ---
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(12)
        scroller.setWidget(inner)
        self.body_layout.addWidget(scroller, stretch=1)

        # --- idea inputs ---
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Title (optional):"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Leave blank to derive from idea")
        title_row.addWidget(self.title_input, stretch=1)
        inner_layout.addLayout(title_row)

        inner_layout.addWidget(QLabel("Idea"))
        self.idea_input = QPlainTextEdit()
        self.idea_input.setPlaceholderText("Describe the product idea in a few sentences.")
        self.idea_input.setMinimumHeight(90)
        inner_layout.addWidget(self.idea_input)

        self.run_banner = QLabel("No run yet. Generate a brief to start one.")
        self.run_banner.setStyleSheet("color: #8a90a2; padding: 6px 0;")
        inner_layout.addWidget(self.run_banner)

        # --- step cards ---
        self.brief_card = self._make_card(
            inner_layout, "1. Product Brief",
            "Goals, users, success metrics, assumptions, unknowns.",
            "Generate Brief", self._generate_brief,
        )

        self.prfaq_card = self._make_card(
            inner_layout, "2. PR/FAQ",
            "Press-release headline, customer FAQ, internal FAQ, launch criteria.",
            "Generate PR/FAQ", self._generate_prfaq,
            enabled=False,
        )

        self.stack_card = self._make_card(
            inner_layout, "3. Tech Stack Decision",
            "Repository analysis + scored options + recommendation.",
            "Recommend Stack", self._generate_stack,
            enabled=False,
        )
        self.repo_path_input = _editable_combo(
            self.history.get("repo_path"),
            placeholder="Path to repo for tech-stack signal detection",
        )
        self.stack_card.extra_row.addWidget(QLabel("Repo:"))
        self.stack_card.extra_row.addWidget(self.repo_path_input, stretch=1)

        self.rfc_card = self._make_card(
            inner_layout, "4. Architecture RFC",
            "Decision + alternatives + tradeoffs + security + rollout (needs brief + stack).",
            "Draft RFC", self._generate_rfc,
            enabled=False,
        )

        self.roadmap_card = self._make_card(
            inner_layout, "5. Roadmap",
            "12-week plan with milestones and acceptance criteria.",
            "Generate Roadmap", self._generate_roadmap,
            enabled=False,
        )

        self.sprint_card = self._make_card(
            inner_layout, "6. Sprint Plan",
            "Slice of the roadmap for one milestone.",
            "Plan Sprint", self._generate_sprint,
            enabled=False,
        )
        self.milestone_input = QComboBox()
        self.milestone_input.setEditable(True)
        self.milestone_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.milestone_input.lineEdit().setPlaceholderText("Milestone (populated from roadmap)")
        self.sprint_card.extra_row.addWidget(QLabel("Milestone:"))
        self.sprint_card.extra_row.addWidget(self.milestone_input, stretch=1)

        self.issue_plan_card = self._make_card(
            inner_layout, "7. GitHub Issue Plan",
            "Maps roadmap items to GitHub issues. Lands as a pending approval.",
            "Build Issue Plan", self._generate_issue_plan,
            enabled=False,
        )
        self.repo_ref_input = _editable_combo(
            self.history.get("repo_ref"),
            placeholder="owner/repo",
        )
        self.issue_plan_card.extra_row.addWidget(QLabel("Repo ref:"))
        self.issue_plan_card.extra_row.addWidget(self.repo_ref_input, stretch=1)

        self.apply_card = self._make_card(
            inner_layout, "8. Apply",
            "Requires Issue Plan approval. Dry-run by default; uncheck to write to GitHub via `gh`.",
            "Apply", self._apply_plan,
            enabled=False,
        )
        self.dry_run_checkbox = QCheckBox("Dry run")
        self.dry_run_checkbox.setChecked(True)
        self.apply_card.extra_row.addWidget(self.dry_run_checkbox)
        self.apply_card.extra_row.addStretch(1)

        self.pr_card = self._make_card(
            inner_layout, "9. GitHub PR",
            "Create a GitHub PR from the current branch with a run-linked PR summary.",
            "Create PR", self._create_pr,
            enabled=False,
        )
        self.pr_repo_input = _editable_combo(
            self.history.get("repo_ref"),
            placeholder="owner/repo",
        )
        self.pr_head_input = QLineEdit()
        self.pr_head_input.setPlaceholderText("head branch (e.g. feature/my-change)")
        self.pr_base_input = QLineEdit()
        self.pr_base_input.setText("main")
        self.pr_title_input = QLineEdit()
        self.pr_title_input.setPlaceholderText("Optional PR title")
        self.pr_draft_checkbox = QCheckBox("Draft PR")
        self.pr_draft_checkbox.setChecked(True)

        self.pr_card.extra_row.addWidget(QLabel("Repo:"))
        self.pr_card.extra_row.addWidget(self.pr_repo_input, stretch=1)
        self.pr_card.extra_row.addWidget(QLabel("Head:"))
        self.pr_card.extra_row.addWidget(self.pr_head_input, stretch=1)
        self.pr_card.extra_row.addWidget(QLabel("Base:"))
        self.pr_card.extra_row.addWidget(self.pr_base_input)
        self.pr_card.extra_row.addWidget(self.pr_draft_checkbox)

        pr_title_row = QHBoxLayout()
        pr_title_row.addWidget(QLabel("Title:"))
        pr_title_row.addWidget(self.pr_title_input, stretch=1)
        self.pr_card.layout().insertLayout(3, pr_title_row)

        inner_layout.addStretch(1)
        self._refresh_state()

    # -- factory --------------------------------------------------------

    def _make_card(self, parent_layout, name, description, button_text, slot, *, enabled=True):
        card = _StepCard(name, description)
        card.button.setText(button_text)
        card.button.setEnabled(enabled)
        card.button.clicked.connect(slot)
        parent_layout.addWidget(card)
        return card

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._refresh_state()

    # -- step handlers --------------------------------------------------

    def _generate_brief(self) -> None:
        if not self._require_project():
            return
        idea = self.idea_input.toPlainText().strip()
        if not idea:
            QMessageBox.warning(self, "Empty idea", "Describe the idea first.")
            return
        title = self.title_input.text().strip() or None
        self._run_step(self.brief_card, lambda: self.engine.create_brief(idea, title),
                       after=self._on_brief_done)

    def _generate_prfaq(self) -> None:
        if not self._require_run("PR/FAQ"):
            return
        rid = self._run_id
        self._run_step(self.prfaq_card, lambda: self.engine.create_prfaq(rid),
                       after=lambda r: self._on_artifact_done(self.prfaq_card, r))

    def _generate_stack(self) -> None:
        if not self._require_run("tech stack"):
            return
        repo = self.repo_path_input.currentText().strip()
        if not repo:
            QMessageBox.warning(self, "Repo path", "Enter a path to the repo for tech-stack analysis.")
            return
        rid = self._run_id
        self._run_step(
            self.stack_card,
            lambda: self.engine.create_tech_stack(rid, repo),
            after=lambda r: self._on_artifact_done_history(
                self.stack_card, r, history_key="repo_path", history_value=repo,
                history_combo=self.repo_path_input,
            ),
        )

    def _generate_rfc(self) -> None:
        if not self._require_run("RFC"):
            return
        rid = self._run_id
        self._run_step(self.rfc_card, lambda: self.engine.create_rfc(rid),
                       after=lambda r: self._on_artifact_done(self.rfc_card, r))

    def _generate_roadmap(self) -> None:
        if not self._require_run("Roadmap"):
            return
        rid = self._run_id
        self._run_step(self.roadmap_card, lambda: self.engine.create_roadmap(rid),
                       after=lambda r: self._on_artifact_done(self.roadmap_card, r))

    def _generate_sprint(self) -> None:
        if not self._require_run("Sprint"):
            return
        milestone = self.milestone_input.currentText().strip()
        if not milestone:
            QMessageBox.warning(self, "Milestone", "Pick or enter a milestone (e.g. M1).")
            return
        rid = self._run_id
        self._run_step(self.sprint_card, lambda: self.engine.create_sprint(rid, milestone),
                       after=lambda r: self._on_artifact_done(self.sprint_card, r))

    def _generate_issue_plan(self) -> None:
        if not self._require_run("Issue plan"):
            return
        repo = self.repo_ref_input.currentText().strip()
        if not repo or "/" not in repo:
            QMessageBox.warning(self, "Repo ref", "Enter owner/repo (e.g. acme/parallel-agents).")
            return
        rid = self._run_id
        self._run_step(
            self.issue_plan_card,
            lambda: self.engine.create_issue_plan(rid, repo),
            after=lambda r: self._on_artifact_done_history(
                self.issue_plan_card, r, history_key="repo_ref", history_value=repo,
                history_combo=self.repo_ref_input,
            ),
        )

    def _apply_plan(self) -> None:
        if not self._require_run("Apply"):
            return
        dry_run = self.dry_run_checkbox.isChecked()
        if not dry_run:
            confirm = QMessageBox.question(
                self,
                "Confirm live apply",
                "This will create issues and milestones on GitHub via `gh`. "
                "Make sure `gh auth status` is set up. Proceed?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        rid = self._run_id
        self._run_step(
            self.apply_card,
            lambda: self.engine.apply_issue_plan(rid, dry_run=dry_run),
            after=self._on_apply_done,
        )

    def _create_pr(self) -> None:
        if not self._require_run("PR creation"):
            return
        repo = self.pr_repo_input.currentText().strip()
        if not repo or "/" not in repo:
            QMessageBox.warning(self, "Repo ref", "Enter owner/repo (e.g. acme/parallel-agents).")
            return
        head = self.pr_head_input.text().strip()
        if not head:
            QMessageBox.warning(self, "Head branch", "Enter a head branch to create the PR from.")
            return
        base = self.pr_base_input.text().strip() or "main"
        title = self.pr_title_input.text().strip() or None
        draft = self.pr_draft_checkbox.isChecked()
        rid = self._run_id
        self._run_step(
            self.pr_card,
            lambda: self.engine.create_pull_request(
                rid,
                repo_ref=repo,
                head=head,
                base=base,
                title=title,
                draft=draft,
            ),
            after=self._on_pr_done,
        )

    # -- helpers --------------------------------------------------------

    def _require_project(self) -> bool:
        if self.engine.current_project() is None:
            QMessageBox.warning(self, "No project", "Open a project first.")
            return False
        return True

    def _require_run(self, step_name: str) -> bool:
        if not self._require_project():
            return False
        if self._run_id is None:
            QMessageBox.warning(self, "No run", f"Generate a Brief before {step_name}.")
            return False
        return True

    def _run_step(self, card, work, after) -> None:
        card.button.setEnabled(False)
        card.set_status("running…", "WorkerStatusRunning")

        async def _job():
            return work()

        self._job = AsyncJob(_job)
        self._job.finished_ok.connect(after)
        self._job.failed.connect(lambda err, c=card: self._on_failed(c, err))
        self._job.start()

    def _on_brief_done(self, result) -> None:
        self._run_id = result.run_id
        self.brief_card.set_status("done", "WorkerStatusDone")
        self.brief_card.button.setEnabled(True)
        self.run_banner.setText(f"Current run: {result.run_id}")
        self.artifact_created.emit(result.run_id, result.artifact_path)
        self._refresh_state()

    def _on_artifact_done(self, card, result) -> None:
        card.set_status("done", "WorkerStatusDone")
        card.button.setEnabled(True)
        self.artifact_created.emit(result.run_id, result.artifact_path)
        self._refresh_state()

    def _on_artifact_done_history(
        self,
        card,
        result,
        *,
        history_key: str,
        history_value: str,
        history_combo: QComboBox,
    ) -> None:
        # only record on success; we're inside `after` so this fired
        self.history.add(history_key, history_value)
        # repopulate the combo's drop-down list with the fresh history
        current = history_combo.currentText()
        history_combo.blockSignals(True)
        history_combo.clear()
        history_combo.addItems(self.history.get(history_key))
        history_combo.setCurrentText(current)
        history_combo.blockSignals(False)
        self._on_artifact_done(card, result)

    def _on_apply_done(self, result) -> None:
        self.apply_card.set_status("done", "WorkerStatusDone")
        self.apply_card.button.setEnabled(True)
        mode = result.get("mode", "dry-run")
        if mode == "dry-run":
            msg = (
                f"Would create {result['issues_planned']} issues across "
                f"{len(result.get('milestones', []))} milestone(s) in {result['repo']}."
            )
        else:
            created = sum(1 for i in result.get("issues", []) if i.get("created"))
            msg = (
                f"Created {created}/{result['issues_planned']} issues in {result['repo']}."
            )
        QMessageBox.information(self, f"Apply complete ({mode})", msg)
        self._refresh_state()

    def _on_pr_done(self, result) -> None:
        self.pr_card.set_status("done", "WorkerStatusDone")
        self.pr_card.button.setEnabled(True)
        self.history.add("repo_ref", result.repo)
        self.artifact_created.emit(result.run_id, result.artifact_path)
        QMessageBox.information(
            self,
            "PR created",
            (
                f"PR URL:\n{result.url}\n\n"
                f"Repo: {result.repo}\n"
                f"Head -> Base: {result.head} -> {result.base}\n"
                f"Draft: {'yes' if result.draft else 'no'}\n"
                f"Summary: {result.summary_path}"
            ),
        )
        self._refresh_state()

    def _on_failed(self, card, error: str) -> None:
        from parallel_agents.desktop.widgets.error_dialog import show_error

        card.set_status("error", "WorkerStatusError")
        card.button.setEnabled(True)
        show_error(
            self,
            "Step failed",
            "The step could not complete. See details for the full error.",
            details=error,
        )

    def _refresh_state(self) -> None:
        if self.engine.current_project() is None:
            return
        if self._run_id is None:
            latest = self.engine.latest_run_id()
            if latest is not None:
                self._run_id = latest
                self.run_banner.setText(f"Resuming latest run: {latest}")
        if self._run_id is None:
            return

        artifacts = self.engine.artifact_names_for_run(self._run_id)

        def _mark(card, name):
            if name in artifacts:
                card.set_status("done", "WorkerStatusDone")

        _mark(self.brief_card, "brief")
        _mark(self.prfaq_card, "prfaq")
        _mark(self.stack_card, "tech-stack")
        _mark(self.rfc_card, "rfc")
        _mark(self.roadmap_card, "roadmap")
        _mark(self.sprint_card, "sprint")
        _mark(self.issue_plan_card, "issue-plan")
        _mark(self.apply_card, "issue-plan-apply")
        _mark(self.pr_card, "pr-create")

        brief_done = "brief" in artifacts
        roadmap_done = "roadmap" in artifacts
        stack_done = "tech-stack" in artifacts
        plan_done = "issue-plan" in artifacts

        self.prfaq_card.button.setEnabled(brief_done)
        self.stack_card.button.setEnabled(brief_done)
        self.rfc_card.button.setEnabled(brief_done and stack_done)
        self.roadmap_card.button.setEnabled(brief_done)
        self.sprint_card.button.setEnabled(roadmap_done)
        self.issue_plan_card.button.setEnabled(roadmap_done)

        # repopulate milestone combo whenever roadmap state changes
        if roadmap_done:
            milestones = self.engine.roadmap_milestones(self._run_id)
            current = self.milestone_input.currentText()
            self.milestone_input.blockSignals(True)
            self.milestone_input.clear()
            self.milestone_input.addItems(milestones)
            if current:
                self.milestone_input.setCurrentText(current)
            elif milestones:
                self.milestone_input.setCurrentIndex(0)
            self.milestone_input.blockSignals(False)

        # apply is gated on a literal approved status, not just artifact presence
        plan_approval_ok = False
        if plan_done:
            approval = self.engine._find_approval(self._run_id, artifact="issue-plan")
            plan_approval_ok = (
                approval is not None
                and approval["data"].get("status") == "approved"
            )
        self.apply_card.button.setEnabled(plan_approval_ok)
        if plan_done and not plan_approval_ok:
            self.apply_card.set_status("awaiting approval", "WorkerStatusIdle")

        pr_ready = (
            plan_done
            or "issue-plan-apply" in artifacts
            or "final-output" in artifacts
        )
        self.pr_card.button.setEnabled(pr_ready)

        if not self.pr_head_input.text().strip():
            try:
                home = self.engine.workspace_home()
                if home.current_branch:
                    self.pr_head_input.setText(home.current_branch)
            except Exception:
                pass
