import asyncio
import unittest
from models import detect_profile, get_profile
from powerlink import BluetoothWorker
from runtime_estimate import RuntimeEstimator

class ModelTests(unittest.TestCase):
    def test_detection_is_explicit_and_longest_model_wins(self):
        self.assertEqual(detect_profile('AC180P12345678').model,'AC180P')
        self.assertEqual(detect_profile('AC18012345678').model,'AC180')
        for name in ('AC180T1234','AC180P-UNKNOWN','AC200L123','SomeOtherStation'):
            self.assertIsNone(detect_profile(name))
        with self.assertRaises(ValueError): get_profile('UNKNOWN')

    def test_common_register_map_matches_upstream_models(self):
        for model in ('AC180','AC180P'):
            fields={f.name:f.address for f in get_profile(model).device_factory().fields}
            self.assertEqual(fields['total_battery_percent'],102)
            self.assertEqual(fields['dc_output_power'],140)
            self.assertEqual(fields['ac_output_power'],142)
            self.assertEqual(fields['ctrl_ac'],2011)
            self.assertEqual(fields['ctrl_dc'],2012)
            self.assertEqual(fields['ctrl_charging_mode'],2020)

    def test_model_capacity_changes_runtime(self):
        small=RuntimeEstimator(capacity_wh=get_profile('AC180').capacity_wh)
        large=RuntimeEstimator(capacity_wh=get_profile('AC180P').capacity_wh)
        self.assertAlmostEqual(small.update(100,0,200,0)/large.update(100,0,200,0),.8)

    def test_experimental_model_cannot_write(self):
        worker=BluetoothWorker()
        worker.profile=get_profile('AC180')
        with self.assertRaisesRegex(RuntimeError,'читання'):
            asyncio.run(worker.write('ctrl_ac',True))

if __name__=='__main__': unittest.main()
