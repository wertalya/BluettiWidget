"""Render fixture states. All readings in these images are synthetic demo data."""
import math
import tempfile
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.widget import Panel, SIZES, STYLE
from app.feedback import FeedbackDialog

app = QApplication([])
app.setStyleSheet(STYLE)
app.setQuitOnLastWindowClosed(False)
output = Path(__file__).resolve().parent.parent / 'qa'
output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    panel = Panel(demo=True, start_worker=False, settings_path=Path(tmp)/'settings.ini')
    panel.show()
    for name in SIZES:
        panel.apply_size(name)
        app.processEvents()
        panel.grab().save(str(output/f'compact_{name}.png'))
    panel.apply_size('M')
    now = time.monotonic()
    panel.history.samples.clear()
    for seconds in range(601):
        panel.history.add(now-600+seconds, 1400+60*math.sin(seconds/18),
                          250+100*math.sin(seconds/37))
    panel.open_details()
    app.processEvents()
    panel.details.grab().save(str(output/'details.png'))
    panel.update_reading({'total_battery_percent':81,'ac_input_power':0,
        'dc_input_power':0,'ac_output_power':340,'dc_output_power':0,
        'ctrl_ac':True,'ctrl_dc':False,'ctrl_charging_mode':'TURBO'})
    panel.set_status('Демонстрація · приклад оцінки часу')
    panel.cluster.animation.stop()
    panel.cluster.values=[0,340]
    app.processEvents()
    panel.grab().save(str(output/'runtime.png'))
    panel.failed('Перепідключаюся · показано останні дані')
    app.processEvents()
    panel.grab().save(str(output/'stale.png'))
    panel.on_paused(True)
    app.processEvents()
    panel.grab().save(str(output/'phone.png'))
    feedback=FeedbackDialog('AC180P',panel)
    feedback.title.setText('Побажання для приборки')
    feedback.description.setPlainText('Опишіть тут свою ідею або кроки відтворення проблеми.')
    feedback.show()
    app.processEvents()
    feedback.grab().save(str(output/'feedback.png'))
    feedback.close()
    panel.shutdown()
