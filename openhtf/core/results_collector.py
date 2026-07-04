from typing import List

from openhtf.core import test_record

class ResultsCollector:
    def __init__(self):
        self._results = []

    def on_test_completed(self, test_record: test_record.TestRecord):
        self._results.append(test_record)

    def get_results(self) -> List[test_record.TestRecord]:
        return self._results