"""Small PyROOT adapter for the selected-tree branch subset used by angle jobs."""
from __future__ import annotations

import numpy as np


class RootTreeArrays:
    """Read requested selected-tree branches entry by entry into array columns."""

    def __init__(self, input_path: str, tree_name: str = "selected"):
        import ROOT

        self._file = ROOT.TFile.Open(str(input_path))
        if not self._file or self._file.IsZombie():
            raise OSError(f"Could not open ROOT file: {input_path}")
        self._tree = self._file.Get(tree_name)
        if not self._tree:
            self._file.Close()
            raise KeyError(f"Tree {tree_name!r} not found in {input_path}")
        self.num_entries = int(self._tree.GetEntries())

    def arrays(self, branches, library="np", entry_stop=None):
        if library != "np":
            raise ValueError("RootTreeArrays supports library='np' only")
        branches = list(branches)
        n = self.num_entries if entry_stop is None else min(self.num_entries, int(entry_stop))
        self._tree.SetBranchStatus("*", 0)
        for name in branches:
            if not self._tree.GetBranch(name):
                raise KeyError(f"Branch {name!r} not found in selected tree")
            self._tree.SetBranchStatus(name, 1)

        result = {}
        for name in branches:
            result[name] = np.empty(n, dtype=np.float64)
        for i in range(n):
            nbytes = self._tree.GetEntry(i)
            if nbytes < 0:
                raise OSError(f"Failed to read entry {i} from selected tree")
            for name in branches:
                value = getattr(self._tree, name)
                if np.isscalar(value):
                    result[name][i] = value
                else:
                    if result[name].dtype != object:
                        result[name] = np.empty(n, dtype=object)
                    result[name][i] = np.asarray(value).copy()
        return result

    def close(self):
        if self._file:
            self._file.Close()
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
