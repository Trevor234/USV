"""Fixture-only finite owned cleanup with observer draining.

The production supervisor and production DDS endpoint settings are unchanged.
An observer error is recorded and cannot skip the remaining owned cleanup.
"""
import time
from owned_process_supervisor import Supervisor, finite_seconds

class ObservingSupervisor(Supervisor):
    observer_pump = None

    def __init__(self, directory):
        super().__init__(directory)
        self.observer_errors = []

    def pump_observer(self, interval):
        try:
            self.observer_pump(interval)
        except BaseException as error:
            self.observer_errors.append(repr(error))
            self.observer_pump = lambda seconds: time.sleep(seconds)
            self.event('cleanup_observer_error', error=repr(error))
            time.sleep(interval)

    def wait_empty(self, item, timeout):
        if self.observer_pump is None:
            return super().wait_empty(item, timeout)
        deadline = time.monotonic() + finite_seconds(timeout)
        while True:
            item.process.poll()
            if not self.members(item):
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            interval = min(.01, remaining)
            self.pump_observer(interval)
