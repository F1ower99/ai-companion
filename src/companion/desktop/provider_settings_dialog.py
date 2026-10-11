from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
)

from companion.domain.chat import (
    ChatContextPreferences,
    ChatSettings,
    PersonalityProfile,
    ProviderConfiguration,
    consent_fingerprint,
)
from companion.domain.errors import StorageError, ValidationError
from companion.infrastructure.windows_credentials import CredentialStoreError


class ProviderSettingsDialog(QDialog):
    saved = Signal(object)

    def __init__(self, settings_repository, secret_store, clock, parent=None) -> None:
        super().__init__(parent)
        self.settings_repository = settings_repository
        self.secret_store = secret_store
        self.clock = clock
        self.setWindowTitle("Companion 提供方设置")
        self.setMinimumWidth(360)

        self.base_url_input = QLineEdit()
        self.base_url_input.setObjectName("providerBaseUrl")
        self.base_url_input.setPlaceholderText("https://api.example.com/v1")
        self.model_input = QLineEdit()
        self.model_input.setObjectName("providerModel")
        self.timeout_input = QSpinBox()
        self.timeout_input.setObjectName("providerTimeout")
        self.timeout_input.setRange(5, 120)
        self.timeout_input.setSuffix(" 秒")

        self.recent_history_checkbox = QCheckBox("最多 12 条近期对话")
        self.saved_memories_checkbox = QCheckBox("最多 5 条相关保存记忆")
        self.today_plan_checkbox = QCheckBox("最多 12 项任务与 8 门课程摘要")

        self.language_input = QLineEdit()
        self.tone_input = QLineEdit()
        self.principles_input = QPlainTextEdit()
        self.principles_input.setPlaceholderText("每行一条 Companion 原则")
        self.principles_input.setMaximumHeight(82)

        self.api_key_input = QLineEdit()
        self.api_key_input.setObjectName("providerSecret")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("只保存在 Windows Credential Manager")
        self.remove_key_checkbox = QCheckBox("保存时移除已保存的密钥")
        self.api_key_input.textChanged.connect(self._key_text_changed)

        self.status_label = QLabel("密钥不会写入本地设置文件或对话。")
        self.status_label.setObjectName("providerSettingsStatus")
        self.status_label.setWordWrap(True)
        self.save_button = QPushButton("保存")
        self.save_button.setObjectName("saveProviderSettings")
        self.cancel_button = QPushButton("取消")
        self.save_button.clicked.connect(self.save_settings)
        self.cancel_button.clicked.connect(self.reject)

        form = QFormLayout()
        form.addRow("HTTPS 提供方地址", self.base_url_input)
        form.addRow("模型", self.model_input)
        form.addRow("超时", self.timeout_input)
        form.addRow("发送到模型的可选上下文", self._context_widget())
        form.addRow("回复语言", self.language_input)
        form.addRow("语气", self.tone_input)
        form.addRow("行为原则", self.principles_input)
        form.addRow("API 密钥", self.api_key_input)
        form.addRow("", self.remove_key_checkbox)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.save_button)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status_label)
        layout.addLayout(buttons)
        self._load_settings()

    def _context_widget(self):
        from PySide6.QtWidgets import QWidget

        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.recent_history_checkbox)
        layout.addWidget(self.saved_memories_checkbox)
        layout.addWidget(self.today_plan_checkbox)
        return widget

    def _load_settings(self) -> None:
        try:
            settings = self.settings_repository.get()
        except Exception:
            self.status_label.setText("本地设置暂时不可用，无法读取设置。")
            self.save_button.setEnabled(False)
            return
        provider = settings.provider
        if provider is not None:
            self.base_url_input.setText(provider.base_url)
            self.model_input.setText(provider.model)
            self.timeout_input.setValue(provider.timeout_seconds)
        context = settings.context_preferences
        self.recent_history_checkbox.setChecked(context.recent_history)
        self.saved_memories_checkbox.setChecked(context.saved_memories)
        self.today_plan_checkbox.setChecked(context.today_plan)
        self.language_input.setText(settings.personality.response_language)
        self.tone_input.setText(settings.personality.tone)
        self.principles_input.setPlainText("\n".join(settings.personality.principles))

    def _key_text_changed(self, value: str) -> None:
        if value:
            self.remove_key_checkbox.setChecked(False)

    def save_settings(self) -> None:
        try:
            old_settings = self.settings_repository.get()
            provider = ProviderConfiguration(
                self.base_url_input.text(),
                self.model_input.text(),
                self.timeout_input.value(),
            )
            preferences = ChatContextPreferences(
                recent_history=self.recent_history_checkbox.isChecked(),
                saved_memories=self.saved_memories_checkbox.isChecked(),
                today_plan=self.today_plan_checkbox.isChecked(),
            )
            principles = tuple(
                line.strip()
                for line in self.principles_input.toPlainText().splitlines()
                if line.strip()
            )
            personality = PersonalityProfile(
                response_language=self.language_input.text(),
                tone=self.tone_input.text(),
                principles=principles,
            )
            if self.remove_key_checkbox.isChecked() and self.api_key_input.text().strip():
                self.status_label.setText("请单独选择保存新密钥或移除现有密钥。")
                return
            new_fingerprint = consent_fingerprint(provider, preferences)
            consent = (
                old_settings.consent_fingerprint
                if old_settings.consent_fingerprint == new_fingerprint
                else None
            )
            updated = ChatSettings(
                provider=provider,
                context_preferences=preferences,
                personality=personality,
                consent_fingerprint=consent,
            )
            self.settings_repository.save(updated, self.clock.now_utc())
        except ValidationError:
            self.status_label.setText("请检查 HTTPS 地址、模型和 Companion 设置。")
            return
        except Exception:
            self.status_label.setText("本地设置暂时不可用，设置未保存。")
            return

        self.saved.emit(updated)
        try:
            if self.remove_key_checkbox.isChecked():
                self.secret_store.delete()
            elif self.api_key_input.text():
                self.secret_store.set(self.api_key_input.text())
        except CredentialStoreError:
            self.status_label.setText("Windows 凭据存储不可用，密钥未保存。")
            return
        except Exception:
            self.status_label.setText("Windows 凭据存储不可用，密钥未保存。")
            return

        self.api_key_input.clear()
        self.remove_key_checkbox.setChecked(False)
        self.status_label.setText("设置已保存在本地。")
        self.accept()
