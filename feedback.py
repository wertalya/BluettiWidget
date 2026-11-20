"""User-reviewed public GitHub issue drafts; never send logs or device identifiers."""
from urllib.parse import urlencode
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
    QLineEdit,QPlainTextEdit,QPushButton,QCheckBox)

VERSION = '0.2.0-preview'
REPOSITORY = 'https://github.com/wertalya/BluettiWidget'

def issue_url(kind,title,description,model=None):
    body = '## '+('Проблема' if kind=='bug' else 'Побажання')+'\n\n'+description.strip()
    if model:
        # Only an explicit profile key is allowed, not the advertising name/SN.
        from models import get_profile
        from platform import system, release
        model = get_profile(model).model
        body += f'\n\n## Середовище\nBluettiWidget: {VERSION}\nМодель: {model}\nОС: {system()} {release()}'
    prefix = '[Bug] ' if kind=='bug' else '[Idea] '
    return REPOSITORY+'/issues/new?'+urlencode({'title':prefix+title.strip(),'body':body})

class FeedbackDialog(QDialog):
    def __init__(self,model,parent=None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle('Написати автору · BluettiWidget')
        self.setMinimumWidth(450)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(22,22,22,22)
        heading=QLabel('Допоможи покращити BluettiWidget')
        heading.setStyleSheet('font-size:19px;font-weight:600;')
        layout.addWidget(heading)
        self.kind=QComboBox()
        self.kind.addItem('Повідомити про проблему','bug')
        self.kind.addItem('Запропонувати покращення','idea')
        layout.addWidget(self.kind)
        self.title=QLineEdit()
        self.title.setPlaceholderText('Коротко: що сталося або чого бракує?')
        self.title.setAccessibleName('Заголовок звернення')
        self.title.setMaxLength(150)
        layout.addWidget(self.title)
        self.description=QPlainTextEdit()
        self.description.setPlaceholderText('Опиши кроки, очікуваний результат або свою ідею…')
        self.description.setAccessibleName('Опис проблеми або побажання')
        self.description.setMinimumHeight(150)
        layout.addWidget(self.description)
        self.context=QCheckBox('Додати версію програми, модель станції та версію ОС')
        layout.addWidget(self.context)
        note=QLabel('Відкриється чернетка публічного звернення на GitHub.\n'
                    'Переглянь текст перед публікацією. Потрібен акаунт GitHub.\n'
                    'Журнали, Bluetooth-адреса й серійний номер не додаються.')
        note.setObjectName('muted'); note.setWordWrap(True)
        layout.addWidget(note)
        row=QHBoxLayout()
        cancel=QPushButton('Скасувати'); cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        self.open_button=QPushButton('Переглянути на GitHub')
        self.open_button.setObjectName('primary')
        self.open_button.setEnabled(False)
        self.title.textChanged.connect(lambda text:self.open_button.setEnabled(bool(text.strip())))
        self.open_button.clicked.connect(self.open_draft)
        row.addWidget(self.open_button)
        layout.addLayout(row)

    def open_draft(self):
        url=issue_url(self.kind.currentData(),self.title.text(),
            self.description.toPlainText(),self.model if self.context.isChecked() else None)
        if QDesktopServices.openUrl(QUrl(url)):
            self.accept()
