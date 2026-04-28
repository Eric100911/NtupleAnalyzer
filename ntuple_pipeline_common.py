#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Common helpers for the assocPV ntuple analysis workflow."""

from __future__ import annotations

import os
import glob
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import ROOT


TREE_NAME = "mkcands/X_data"
OUTPUT_BASE = "/eos/user/c/chiw/JpsiJpsiUps/NtupleAnalyzer_assocPV"
DEFAULT_PROXY = "/afs/cern.ch/user/c/chiw/condor/x509up"

DATA_PATHS = {
    "JJP": "/eos/user/c/chiw/JpsiJpsiPhi/rootNtuple",
    "JUP": "/eos/user/c/chiw/JpsiUpsPhi/rootNtuple",
}

JJP_DATASET_DIRS = tuple(f"ParkingDoubleMuonLowMass{i}" for i in range(8))
JJP_REFACTOR_PREFIX = "crab3_refactor"
JJP_SUBMIT_PREFIX = "260411"
JUP_DATASET_DIRS = tuple(f"ParkingDoubleMuonLowMass{i}" for i in range(8))
JUP_REFACTOR_PREFIX = "crab3_JpsiUpsPhi_refactor"
JUP_SUBMIT_PREFIX = "2604"

MC_BASE = "/eos/ihep/cms/store/user/xcheng/MC_Production_v2/output"
JJY_MC_BASE = "/eos/user/c/chiw/JpsiJpsiUps/MC_samples/rootNtuple_refactor"
MC_SAMPLE_DIRS = {
    "JJP": {
        "SPS": "JJP_SPS",
        "DPS": "JJP_DPS2",
        "DPS1": "JJP_DPS1",
        "DPS_1": "JJP_DPS1",
        "DPS2": "JJP_DPS2",
        "DPS_2": "JJP_DPS2",
        "TPS": "JJP_TPS",
    },
    "JUP": {
        "SPS": "JUP_SPS",
        "DPS_1": "JUP_DPS1",
        "DPS_2": "JUP_DPS2",
        "DPS_3": "JUP_DPS3",
        "TPS": "JUP_TPS",
    },
    "JJY": {
        "DPS_1": "DPS-Jpsi-JpsiY/filter_JpsiPtMin4p0_YPtMin6p0",
        "DPS_2": "DPS-JpsiJpsi-Y/filter_JpsiPtMin4p0_YPtMin6p0",
    },
}

MUON_ID_BRANCHES = {
    "none": None,
    "loose": "muIsPatLooseMuon",
    "medium": "muIsPatMediumMuon",
    "tight": "muIsPatTightMuon",
    "soft": "muIsPatSoftMuon",
}


@dataclass(frozen=True)
class ChannelConfig:
    channel: str
    mass_branches: Tuple[str, ...]
    fit_branches: Tuple[str, ...]
    pair_specs: Tuple[Tuple[str, str, str], ...]
    selected_candidate_branches: Tuple[str, ...]
    selected_muon_specs: Tuple[Tuple[str, str], ...]
    selected_kaon_specs: Tuple[Tuple[str, str], ...]


@dataclass(frozen=True)
class DatasetSchema:
    schema_key: str
    channel: str
    dataset: str
    best_index_kind: str
    selected_branch_map: Tuple[Tuple[str, str], ...]
    selected_muon_specs: Tuple[Tuple[str, str], ...]
    selected_particle_prefixes: Tuple[str, ...]


CHANNEL_CONFIGS: Dict[str, ChannelConfig] = {
    "JJP": ChannelConfig(
        channel="JJP",
        mass_branches=("sel_Jpsi_1_mass", "sel_Jpsi_2_mass", "sel_Phi_mass"),
        fit_branches=("sel_Jpsi_1_mass", "sel_Jpsi_2_mass", "sel_Phi_mass"),
        pair_specs=(
            ("jpsi1_jpsi2", "sel_Jpsi_1", "sel_Jpsi_2"),
            ("jpsi1_phi", "sel_Jpsi_1", "sel_Phi"),
            ("jpsi2_phi", "sel_Jpsi_2", "sel_Phi"),
        ),
        selected_candidate_branches=(
            "Jpsi_1_mass",
            "Jpsi_1_massErr",
            "Jpsi_1_massDiff",
            "Jpsi_1_ctau",
            "Jpsi_1_ctauErr",
            "Jpsi_1_Chi2",
            "Jpsi_1_ndof",
            "Jpsi_1_VtxProb",
            "Jpsi_1_px",
            "Jpsi_1_py",
            "Jpsi_1_pz",
            "Jpsi_1_phi",
            "Jpsi_1_eta",
            "Jpsi_1_pt",
            "Jpsi_1_mu_1_Idx",
            "Jpsi_1_mu_2_Idx",
            "Jpsi_2_mass",
            "Jpsi_2_massErr",
            "Jpsi_2_massDiff",
            "Jpsi_2_ctau",
            "Jpsi_2_ctauErr",
            "Jpsi_2_Chi2",
            "Jpsi_2_ndof",
            "Jpsi_2_VtxProb",
            "Jpsi_2_px",
            "Jpsi_2_py",
            "Jpsi_2_pz",
            "Jpsi_2_phi",
            "Jpsi_2_eta",
            "Jpsi_2_pt",
            "Jpsi_2_mu_1_Idx",
            "Jpsi_2_mu_2_Idx",
            "Phi_mass",
            "Phi_massErr",
            "Phi_massDiff",
            "Phi_ctau",
            "Phi_ctauErr",
            "Phi_Chi2",
            "Phi_ndof",
            "Phi_VtxProb",
            "Phi_px",
            "Phi_py",
            "Phi_pz",
            "Phi_phi",
            "Phi_eta",
            "Phi_pt",
            "Phi_K_1_Idx",
            "Phi_K_2_Idx",
            "Phi_K_1_px",
            "Phi_K_1_py",
            "Phi_K_1_pz",
            "Phi_K_1_phi",
            "Phi_K_1_eta",
            "Phi_K_1_pt",
            "Phi_K_2_px",
            "Phi_K_2_py",
            "Phi_K_2_pz",
            "Phi_K_2_phi",
            "Phi_K_2_eta",
            "Phi_K_2_pt",
            "Pri_mass",
            "Pri_massErr",
            "Pri_ctau",
            "Pri_ctauErr",
            "Pri_Chi2",
            "Pri_ndof",
            "Pri_VtxProb",
            "Pri_px",
            "Pri_py",
            "Pri_pz",
            "Pri_phi",
            "Pri_eta",
            "Pri_pt",
        ),
        selected_muon_specs=(
            ("sel_Jpsi_1_mu_1_Idx", "sel_Jpsi1_mu1"),
            ("sel_Jpsi_1_mu_2_Idx", "sel_Jpsi1_mu2"),
            ("sel_Jpsi_2_mu_1_Idx", "sel_Jpsi2_mu1"),
            ("sel_Jpsi_2_mu_2_Idx", "sel_Jpsi2_mu2"),
        ),
        selected_kaon_specs=(
            ("sel_Phi_K_1", "sel_Phi_K_1"),
            ("sel_Phi_K_2", "sel_Phi_K_2"),
        ),
    ),
    "JUP": ChannelConfig(
        channel="JUP",
        mass_branches=("sel_Jpsi_mass", "sel_Ups_mass", "sel_Phi_mass"),
        fit_branches=("sel_Jpsi_mass", "sel_Ups_mass", "sel_Phi_mass"),
        pair_specs=(
            ("jpsi_ups", "sel_Jpsi", "sel_Ups"),
            ("jpsi_phi", "sel_Jpsi", "sel_Phi"),
            ("ups_phi", "sel_Ups", "sel_Phi"),
        ),
        selected_candidate_branches=(
            "Jpsi_mass",
            "Jpsi_massErr",
            "Jpsi_massDiff",
            "Jpsi_ctau",
            "Jpsi_ctauErr",
            "Jpsi_Chi2",
            "Jpsi_ndof",
            "Jpsi_VtxProb",
            "Jpsi_px",
            "Jpsi_py",
            "Jpsi_pz",
            "Jpsi_phi",
            "Jpsi_eta",
            "Jpsi_pt",
            "Jpsi_mu_1_Idx",
            "Jpsi_mu_2_Idx",
            "Ups_mass",
            "Ups_massErr",
            "Ups_massDiff",
            "Ups_ctau",
            "Ups_ctauErr",
            "Ups_Chi2",
            "Ups_ndof",
            "Ups_VtxProb",
            "Ups_px",
            "Ups_py",
            "Ups_pz",
            "Ups_phi",
            "Ups_eta",
            "Ups_pt",
            "Ups_mu_1_Idx",
            "Ups_mu_2_Idx",
            "Phi_mass",
            "Phi_massErr",
            "Phi_massDiff",
            "Phi_ctau",
            "Phi_ctauErr",
            "Phi_Chi2",
            "Phi_ndof",
            "Phi_VtxProb",
            "Phi_px",
            "Phi_py",
            "Phi_pz",
            "Phi_phi",
            "Phi_eta",
            "Phi_pt",
            "Phi_K_1_Idx",
            "Phi_K_2_Idx",
            "Phi_K_1_px",
            "Phi_K_1_py",
            "Phi_K_1_pz",
            "Phi_K_1_phi",
            "Phi_K_1_eta",
            "Phi_K_1_pt",
            "Phi_K_2_px",
            "Phi_K_2_py",
            "Phi_K_2_pz",
            "Phi_K_2_phi",
            "Phi_K_2_eta",
            "Phi_K_2_pt",
            "Pri_mass",
            "Pri_massErr",
            "Pri_ctau",
            "Pri_ctauErr",
            "Pri_Chi2",
            "Pri_ndof",
            "Pri_VtxProb",
            "Pri_px",
            "Pri_py",
            "Pri_pz",
            "Pri_phi",
            "Pri_eta",
            "Pri_pt",
        ),
        selected_muon_specs=(
            ("sel_Jpsi_mu_1_Idx", "sel_Jpsi_mu1"),
            ("sel_Jpsi_mu_2_Idx", "sel_Jpsi_mu2"),
            ("sel_Ups_mu_1_Idx", "sel_Ups_mu1"),
            ("sel_Ups_mu_2_Idx", "sel_Ups_mu2"),
        ),
        selected_kaon_specs=(
            ("sel_Phi_K_1", "sel_Phi_K_1"),
            ("sel_Phi_K_2", "sel_Phi_K_2"),
        ),
    ),
    "JJY": ChannelConfig(
        channel="JJY",
        mass_branches=("sel_Jpsi_1_mass", "sel_Jpsi_2_mass", "sel_Ups_mass"),
        fit_branches=("sel_Jpsi_1_mass", "sel_Jpsi_2_mass", "sel_Ups_mass"),
        pair_specs=(
            ("jpsi1_jpsi2", "sel_Jpsi_1", "sel_Jpsi_2"),
            ("jpsi1_ups", "sel_Jpsi_1", "sel_Ups"),
            ("jpsi2_ups", "sel_Jpsi_2", "sel_Ups"),
        ),
        selected_candidate_branches=(
            "Jpsi_1_mass",
            "Jpsi_1_massErr",
            "Jpsi_1_massDiff",
            "Jpsi_1_ctau",
            "Jpsi_1_ctauErr",
            "Jpsi_1_Chi2",
            "Jpsi_1_ndof",
            "Jpsi_1_VtxProb",
            "Jpsi_1_px",
            "Jpsi_1_py",
            "Jpsi_1_pz",
            "Jpsi_1_phi",
            "Jpsi_1_eta",
            "Jpsi_1_pt",
            "Jpsi_1_mu_1_Idx",
            "Jpsi_1_mu_2_Idx",
            "Jpsi_2_mass",
            "Jpsi_2_massErr",
            "Jpsi_2_massDiff",
            "Jpsi_2_ctau",
            "Jpsi_2_ctauErr",
            "Jpsi_2_Chi2",
            "Jpsi_2_ndof",
            "Jpsi_2_VtxProb",
            "Jpsi_2_px",
            "Jpsi_2_py",
            "Jpsi_2_pz",
            "Jpsi_2_phi",
            "Jpsi_2_eta",
            "Jpsi_2_pt",
            "Jpsi_2_mu_1_Idx",
            "Jpsi_2_mu_2_Idx",
            "Ups_mass",
            "Ups_massErr",
            "Ups_massDiff",
            "Ups_ctau",
            "Ups_ctauErr",
            "Ups_Chi2",
            "Ups_ndof",
            "Ups_VtxProb",
            "Ups_px",
            "Ups_py",
            "Ups_pz",
            "Ups_phi",
            "Ups_eta",
            "Ups_pt",
            "Ups_mu_1_Idx",
            "Ups_mu_2_Idx",
            "Pri_mass",
            "Pri_massErr",
            "Pri_ctau",
            "Pri_ctauErr",
            "Pri_Chi2",
            "Pri_ndof",
            "Pri_VtxProb",
            "Pri_fitValid",
            "Pri_px",
            "Pri_py",
            "Pri_pz",
            "Pri_phi",
            "Pri_eta",
            "Pri_pt",
        ),
        selected_muon_specs=(
            ("sel_Jpsi_1_mu_1_Idx", "sel_Jpsi1_mu1"),
            ("sel_Jpsi_1_mu_2_Idx", "sel_Jpsi1_mu2"),
            ("sel_Jpsi_2_mu_1_Idx", "sel_Jpsi2_mu1"),
            ("sel_Jpsi_2_mu_2_Idx", "sel_Jpsi2_mu2"),
            ("sel_Ups_mu_1_Idx", "sel_Ups_mu1"),
            ("sel_Ups_mu_2_Idx", "sel_Ups_mu2"),
        ),
        selected_kaon_specs=(),
    ),
}


def normalize_channel(channel: str) -> str:
    channel_up = channel.upper()
    if channel_up not in CHANNEL_CONFIGS:
        raise ValueError(f"Unsupported channel: {channel}")
    return channel_up


def normalize_dataset(dataset: str) -> str:
    dataset_low = dataset.lower()
    if dataset_low not in {"data", "mc"}:
        raise ValueError(f"Unsupported dataset: {dataset}")
    return dataset_low


def normalize_sample(channel: str, sample: str | None) -> str | None:
    if sample is None:
        return None
    if channel == "JJY":
        sample_up = sample.upper()
    else:
        sample_up = sample.upper().replace("DPS1", "DPS_1").replace("DPS2", "DPS_2").replace("DPS3", "DPS_3")
    valid = MC_SAMPLE_DIRS[channel]
    if sample_up not in valid:
        raise ValueError(f"Unsupported sample for {channel}: {sample}")
    return sample_up


def default_input_dir(channel: str, dataset: str, sample: str | None = None) -> str:
    if dataset == "data":
        return DATA_PATHS[channel]
    if sample is None:
        raise ValueError("MC input requires --sample")
    if channel == "JJY":
        return os.path.join(JJY_MC_BASE, MC_SAMPLE_DIRS[channel][sample])
    return os.path.join(MC_BASE, MC_SAMPLE_DIRS[channel][sample])


def make_tag(channel: str, dataset: str, sample: str | None = None) -> str:
    base = f"{channel.lower()}_{dataset}"
    if dataset == "mc" and sample:
        base = f"{base}_{sample.lower()}"
    return base


def default_merged_output(channel: str, dataset: str, sample: str | None = None, output_base: str = OUTPUT_BASE) -> str:
    tag = make_tag(channel, dataset, sample)
    return os.path.join(output_base, "merged", f"{tag}_selected.root")


def default_weighted_output(channel: str, dataset: str, sample: str | None = None, output_base: str = OUTPUT_BASE) -> str:
    tag = make_tag(channel, dataset, sample)
    return os.path.join(output_base, "fit", f"{tag}_weighted.root")


def default_plot_dir(channel: str, dataset: str, sample: str | None = None, output_base: str = OUTPUT_BASE) -> str:
    tag = make_tag(channel, dataset, sample)
    return os.path.join(output_base, "plots", tag)


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def to_xrootd_if_needed(path: str) -> str:
    if path.startswith("root://"):
        return path
    if path.startswith("/eos/ihep/"):
        return f"root://cceos.ihep.ac.cn//{path.lstrip('/')}"
    return path


def _discover_jjp_refactor_data_files(input_path: str) -> List[str]:
    files: List[str] = []
    for dataset_dir in JJP_DATASET_DIRS:
        base_dir = os.path.join(input_path, dataset_dir)
        if not os.path.isdir(base_dir):
            continue

        task_dirs = sorted(glob.glob(os.path.join(base_dir, f"{JJP_REFACTOR_PREFIX}*")))
        for task_dir in task_dirs:
            if not os.path.isdir(task_dir):
                continue

            submit_dirs = sorted(glob.glob(os.path.join(task_dir, f"{JJP_SUBMIT_PREFIX}*")))
            for submit_dir in submit_dirs:
                if not os.path.isdir(submit_dir):
                    continue
                files.extend(sorted(glob.glob(os.path.join(submit_dir, "**", "*.root"), recursive=True)))
    return files


def _discover_jup_refactor_data_files(input_path: str) -> List[str]:
    files: List[str] = []
    for dataset_dir in JUP_DATASET_DIRS:
        base_dir = os.path.join(input_path, dataset_dir)
        if not os.path.isdir(base_dir):
            continue

        task_dirs = sorted(glob.glob(os.path.join(base_dir, f"{JUP_REFACTOR_PREFIX}*")))
        for task_dir in task_dirs:
            if not os.path.isdir(task_dir):
                continue

            submit_dirs = sorted(glob.glob(os.path.join(task_dir, f"{JUP_SUBMIT_PREFIX}*")))
            for submit_dir in submit_dirs:
                if not os.path.isdir(submit_dir):
                    continue
                files.extend(sorted(glob.glob(os.path.join(submit_dir, "**", "*.root"), recursive=True)))
    return files


def discover_root_files(input_path: str, max_files: int = -1) -> List[str]:
    resolved = to_xrootd_if_needed(input_path)
    files: List[str]
    if resolved.endswith(".root"):
        files = [resolved]
    elif resolved.startswith("root://"):
        stripped = resolved[len("root://") :]
        host, remote_path = stripped.split("/", 1)
        remote_path = "/" + remote_path
        cmd = ["xrdfs", host, "ls", "-R", remote_path]
        env = os.environ.copy()
        if "X509_USER_PROXY" not in env and os.path.exists(DEFAULT_PROXY):
            env["X509_USER_PROXY"] = DEFAULT_PROXY
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
        files = [f"root://{host}{line.strip()}" for line in result.stdout.splitlines() if line.strip().endswith("output_ntuple.root")]
        if not files:
            files = [f"root://{host}{line.strip()}" for line in result.stdout.splitlines() if line.strip().endswith(".root")]
    else:
        files = _discover_jjp_refactor_data_files(resolved)
        if not files:
            files = _discover_jup_refactor_data_files(resolved)
        if not files:
            files = sorted(glob.glob(os.path.join(resolved, "*.root")))
        if not files:
            files = sorted(glob.glob(os.path.join(resolved, "**", "*.root"), recursive=True))
    if max_files > 0:
        files = files[:max_files]
    if not files:
        raise FileNotFoundError(f"No ROOT files found under {input_path}")
    return files


def get_tree_branches(file_name: str, tree_name: str = TREE_NAME) -> List[str]:
    try:
        import uproot

        with uproot.open(file_name) as fin:
            return list(fin[tree_name].keys())
    except Exception:
        tf = ROOT.TFile.Open(file_name)
        if not tf or tf.IsZombie():
            raise RuntimeError(f"Failed to open {file_name}")
        tree = tf.Get(tree_name)
        if tree is None:
            raise RuntimeError(f"Tree {tree_name} not found in {file_name}")
        branches = [br.GetName() for br in tree.GetListOfBranches()]
        tf.Close()
        return branches


def build_root_string_vector(items: Sequence[str]):
    out = ROOT.std.vector("string")()
    for item in items:
        out.push_back(item)
    return out


def _jjp_selected_branch_map() -> Tuple[Tuple[str, str], ...]:
    names = [
        "Jpsi_1_mass",
        "Jpsi_1_massErr",
        "Jpsi_1_massDiff",
        "Jpsi_1_ctau",
        "Jpsi_1_ctauErr",
        "Jpsi_1_Chi2",
        "Jpsi_1_ndof",
        "Jpsi_1_VtxProb",
        "Jpsi_1_px",
        "Jpsi_1_py",
        "Jpsi_1_pz",
        "Jpsi_1_phi",
        "Jpsi_1_eta",
        "Jpsi_1_pt",
        "Jpsi_1_mu_1_Idx",
        "Jpsi_1_mu_2_Idx",
        "Jpsi_2_mass",
        "Jpsi_2_massErr",
        "Jpsi_2_massDiff",
        "Jpsi_2_ctau",
        "Jpsi_2_ctauErr",
        "Jpsi_2_Chi2",
        "Jpsi_2_ndof",
        "Jpsi_2_VtxProb",
        "Jpsi_2_px",
        "Jpsi_2_py",
        "Jpsi_2_pz",
        "Jpsi_2_phi",
        "Jpsi_2_eta",
        "Jpsi_2_pt",
        "Jpsi_2_mu_1_Idx",
        "Jpsi_2_mu_2_Idx",
        "Phi_mass",
        "Phi_massErr",
        "Phi_massDiff",
        "Phi_ctau",
        "Phi_ctauErr",
        "Phi_Chi2",
        "Phi_ndof",
        "Phi_VtxProb",
        "Phi_px",
        "Phi_py",
        "Phi_pz",
        "Phi_phi",
        "Phi_eta",
        "Phi_pt",
        "Phi_K_1_Idx",
        "Phi_K_2_Idx",
        "Phi_K_1_px",
        "Phi_K_1_py",
        "Phi_K_1_pz",
        "Phi_K_1_phi",
        "Phi_K_1_eta",
        "Phi_K_1_pt",
        "Phi_K_2_px",
        "Phi_K_2_py",
        "Phi_K_2_pz",
        "Phi_K_2_phi",
        "Phi_K_2_eta",
        "Phi_K_2_pt",
        "Pri_mass",
        "Pri_massErr",
        "Pri_ctau",
        "Pri_ctauErr",
        "Pri_Chi2",
        "Pri_ndof",
        "Pri_VtxProb",
        "Pri_px",
        "Pri_py",
        "Pri_pz",
        "Pri_phi",
        "Pri_eta",
        "Pri_pt",
    ]
    return tuple((name, name) for name in names)


def _jup_selected_branch_map(input_prefix: str) -> Tuple[Tuple[str, str], ...]:
    mapping = [
        ("Jpsi_mass", f"{input_prefix}_mass"),
        ("Jpsi_massErr", f"{input_prefix}_massErr"),
        ("Jpsi_massDiff", f"{input_prefix}_massDiff"),
        ("Jpsi_ctau", f"{input_prefix}_ctau"),
        ("Jpsi_ctauErr", f"{input_prefix}_ctauErr"),
        ("Jpsi_Chi2", f"{input_prefix}_Chi2"),
        ("Jpsi_ndof", f"{input_prefix}_ndof"),
        ("Jpsi_VtxProb", f"{input_prefix}_VtxProb"),
        ("Jpsi_px", f"{input_prefix}_px"),
        ("Jpsi_py", f"{input_prefix}_py"),
        ("Jpsi_pz", f"{input_prefix}_pz"),
        ("Jpsi_phi", f"{input_prefix}_phi"),
        ("Jpsi_eta", f"{input_prefix}_eta"),
        ("Jpsi_pt", f"{input_prefix}_pt"),
        ("Jpsi_mu_1_Idx", f"{input_prefix}_mu_1_Idx"),
        ("Jpsi_mu_2_Idx", f"{input_prefix}_mu_2_Idx"),
        ("Ups_mass", "Ups_mass"),
        ("Ups_massErr", "Ups_massErr"),
        ("Ups_massDiff", "Ups_massDiff"),
        ("Ups_ctau", "Ups_ctau"),
        ("Ups_ctauErr", "Ups_ctauErr"),
        ("Ups_Chi2", "Ups_Chi2"),
        ("Ups_ndof", "Ups_ndof"),
        ("Ups_VtxProb", "Ups_VtxProb"),
        ("Ups_px", "Ups_px"),
        ("Ups_py", "Ups_py"),
        ("Ups_pz", "Ups_pz"),
        ("Ups_phi", "Ups_phi"),
        ("Ups_eta", "Ups_eta"),
        ("Ups_pt", "Ups_pt"),
        ("Ups_mu_1_Idx", "Ups_mu_1_Idx"),
        ("Ups_mu_2_Idx", "Ups_mu_2_Idx"),
        ("Phi_mass", "Phi_mass"),
        ("Phi_massErr", "Phi_massErr"),
        ("Phi_massDiff", "Phi_massDiff"),
        ("Phi_ctau", "Phi_ctau"),
        ("Phi_ctauErr", "Phi_ctauErr"),
        ("Phi_Chi2", "Phi_Chi2"),
        ("Phi_ndof", "Phi_ndof"),
        ("Phi_VtxProb", "Phi_VtxProb"),
        ("Phi_px", "Phi_px"),
        ("Phi_py", "Phi_py"),
        ("Phi_pz", "Phi_pz"),
        ("Phi_phi", "Phi_phi"),
        ("Phi_eta", "Phi_eta"),
        ("Phi_pt", "Phi_pt"),
        ("Phi_K_1_Idx", "Phi_K_1_Idx"),
        ("Phi_K_2_Idx", "Phi_K_2_Idx"),
        ("Phi_K_1_px", "Phi_K_1_px"),
        ("Phi_K_1_py", "Phi_K_1_py"),
        ("Phi_K_1_pz", "Phi_K_1_pz"),
        ("Phi_K_1_phi", "Phi_K_1_phi"),
        ("Phi_K_1_eta", "Phi_K_1_eta"),
        ("Phi_K_1_pt", "Phi_K_1_pt"),
        ("Phi_K_2_px", "Phi_K_2_px"),
        ("Phi_K_2_py", "Phi_K_2_py"),
        ("Phi_K_2_pz", "Phi_K_2_pz"),
        ("Phi_K_2_phi", "Phi_K_2_phi"),
        ("Phi_K_2_eta", "Phi_K_2_eta"),
        ("Phi_K_2_pt", "Phi_K_2_pt"),
        ("Pri_mass", "Pri_mass"),
        ("Pri_massErr", "Pri_massErr"),
        ("Pri_ctau", "Pri_ctau"),
        ("Pri_ctauErr", "Pri_ctauErr"),
        ("Pri_Chi2", "Pri_Chi2"),
        ("Pri_ndof", "Pri_ndof"),
        ("Pri_VtxProb", "Pri_VtxProb"),
        ("Pri_px", "Pri_px"),
        ("Pri_py", "Pri_py"),
        ("Pri_pz", "Pri_pz"),
        ("Pri_phi", "Pri_phi"),
        ("Pri_eta", "Pri_eta"),
        ("Pri_pt", "Pri_pt"),
    ]
    return tuple(mapping)


def _jjy_selected_branch_map() -> Tuple[Tuple[str, str], ...]:
    return tuple((name, name) for name in CHANNEL_CONFIGS["JJY"].selected_candidate_branches)


DATASET_SCHEMAS: Dict[Tuple[str, str], DatasetSchema] = {
    ("JJP", "data"): DatasetSchema(
        schema_key="JJP_data",
        channel="JJP",
        dataset="data",
        best_index_kind="JJP",
        selected_branch_map=_jjp_selected_branch_map(),
        selected_muon_specs=(
            ("Jpsi_1_mu_1_Idx", "sel_Jpsi1_mu1"),
            ("Jpsi_1_mu_2_Idx", "sel_Jpsi1_mu2"),
            ("Jpsi_2_mu_1_Idx", "sel_Jpsi2_mu1"),
            ("Jpsi_2_mu_2_Idx", "sel_Jpsi2_mu2"),
        ),
        selected_particle_prefixes=("sel_Jpsi_1", "sel_Jpsi_2", "sel_Phi", "sel_Pri"),
    ),
    ("JJP", "mc"): DatasetSchema(
        schema_key="JJP_mc",
        channel="JJP",
        dataset="mc",
        best_index_kind="JJP",
        selected_branch_map=_jjp_selected_branch_map(),
        selected_muon_specs=(
            ("Jpsi_1_mu_1_Idx", "sel_Jpsi1_mu1"),
            ("Jpsi_1_mu_2_Idx", "sel_Jpsi1_mu2"),
            ("Jpsi_2_mu_1_Idx", "sel_Jpsi2_mu1"),
            ("Jpsi_2_mu_2_Idx", "sel_Jpsi2_mu2"),
        ),
        selected_particle_prefixes=("sel_Jpsi_1", "sel_Jpsi_2", "sel_Phi", "sel_Pri"),
    ),
    ("JUP", "data"): DatasetSchema(
        schema_key="JUP_data",
        channel="JUP",
        dataset="data",
        best_index_kind="JUP_DATA",
        selected_branch_map=_jup_selected_branch_map("Jpsi"),
        selected_muon_specs=(
            ("Jpsi_mu_1_Idx", "sel_Jpsi_mu1"),
            ("Jpsi_mu_2_Idx", "sel_Jpsi_mu2"),
            ("Ups_mu_1_Idx", "sel_Ups_mu1"),
            ("Ups_mu_2_Idx", "sel_Ups_mu2"),
        ),
        selected_particle_prefixes=("sel_Jpsi", "sel_Ups", "sel_Phi", "sel_Pri"),
    ),
    ("JUP", "mc"): DatasetSchema(
        schema_key="JUP_mc",
        channel="JUP",
        dataset="mc",
        best_index_kind="JUP_MC",
        selected_branch_map=_jup_selected_branch_map("Jpsi_1"),
        selected_muon_specs=(
            ("Jpsi_mu_1_Idx", "sel_Jpsi_mu1"),
            ("Jpsi_mu_2_Idx", "sel_Jpsi_mu2"),
            ("Ups_mu_1_Idx", "sel_Ups_mu1"),
            ("Ups_mu_2_Idx", "sel_Ups_mu2"),
        ),
        selected_particle_prefixes=("sel_Jpsi", "sel_Ups", "sel_Phi", "sel_Pri"),
    ),
    ("JJY", "mc"): DatasetSchema(
        schema_key="JJY_mc",
        channel="JJY",
        dataset="mc",
        best_index_kind="JJY",
        selected_branch_map=_jjy_selected_branch_map(),
        selected_muon_specs=(
            ("Jpsi_1_mu_1_Idx", "sel_Jpsi1_mu1"),
            ("Jpsi_1_mu_2_Idx", "sel_Jpsi1_mu2"),
            ("Jpsi_2_mu_1_Idx", "sel_Jpsi2_mu1"),
            ("Jpsi_2_mu_2_Idx", "sel_Jpsi2_mu2"),
            ("Ups_mu_1_Idx", "sel_Ups_mu1"),
            ("Ups_mu_2_Idx", "sel_Ups_mu2"),
        ),
        selected_particle_prefixes=("sel_Jpsi_1", "sel_Jpsi_2", "sel_Ups", "sel_Pri"),
    ),
}


def get_dataset_schema(channel: str, dataset: str) -> DatasetSchema:
    return DATASET_SCHEMAS[(channel, dataset)]


_RDF_HELPERS_DECLARED = False


def declare_rdf_helpers() -> None:
    global _RDF_HELPERS_DECLARED
    if _RDF_HELPERS_DECLARED:
        return

    ROOT.gInterpreter.Declare(
        r"""
        #include <algorithm>
        #include <cmath>
        #include <vector>
        #include "ROOT/RVec.hxx"

        using ROOT::VecOps::RVec;

        template <typename T>
        T TakeAt(const RVec<T>& values, int idx) {
            if (idx < 0 || idx >= static_cast<int>(values.size())) {
                return T{};
            }
            return values[idx];
        }

        int TakeAtInt(const RVec<float>& values, int idx) {
            if (idx < 0 || idx >= static_cast<int>(values.size())) {
                return -1;
            }
            return static_cast<int>(values[idx]);
        }

        RVec<int> OnesLike(const RVec<float>& values) {
            return RVec<int>(values.size(), 1);
        }

        float PtFromPxPy(float px, float py) {
            return std::sqrt(px * px + py * py);
        }

        float PhiFromPxPy(float px, float py) {
            return std::atan2(py, px);
        }

        float EtaFromPxyz(float px, float py, float pz) {
            const float p = std::sqrt(px * px + py * py + pz * pz);
            const float denom = p - pz;
            if (denom <= 0.f) {
                return (pz >= 0.f) ? 1e6f : -1e6f;
            }
            return 0.5f * std::log((p + pz) / denom);
        }

        float RapidityFromPtEtaM(float pt, float eta, float mass) {
            const double pz = pt * std::sinh(static_cast<double>(eta));
            const double p2 = pt * pt + pz * pz;
            const double energy = std::sqrt(p2 + static_cast<double>(mass) * mass);
            const double denom = energy - pz;
            if (denom <= 0.) {
                return (pz >= 0.) ? 1e6f : -1e6f;
            }
            return static_cast<float>(0.5 * std::log((energy + pz) / denom));
        }

        float DeltaPhiAbs(float phi1, float phi2) {
            float dphi = phi1 - phi2;
            while (dphi > M_PI) dphi -= 2.f * M_PI;
            while (dphi < -M_PI) dphi += 2.f * M_PI;
            return std::fabs(dphi);
        }

        bool PassMuonRecoKinematics(float px, float py, float pz) {
            const float pt = PtFromPxPy(px, py);
            const float abs_eta = std::fabs(EtaFromPxyz(px, py, pz));
            if (abs_eta < 1.2f) {
                return pt > 3.5f;
            }
            if (abs_eta < 2.4f) {
                return pt > 2.5f;
            }
            return false;
        }

        bool PassMuonSelection(
            const RVec<float>& muPx,
            const RVec<float>& muPy,
            const RVec<float>& muPz,
            const RVec<int>& muIdMask,
            int idx
        ) {
            if (idx < 0 || idx >= static_cast<int>(muPx.size()) ||
                idx >= static_cast<int>(muPy.size()) ||
                idx >= static_cast<int>(muPz.size()) ||
                idx >= static_cast<int>(muIdMask.size())) {
                return false;
            }
            return muIdMask[idx] > 0 && PassMuonRecoKinematics(muPx[idx], muPy[idx], muPz[idx]);
        }

        bool PassGenMotherMatch(
            int genIdx,
            int genMatchSource,
            const RVec<int>& genMotherIdx,
            const RVec<int>& genMotherPdgId,
            int requiredMotherPdgId
        ) {
            if (genMatchSource != 1) {
                return false;
            }
            if (genIdx < 0 || genIdx >= static_cast<int>(genMotherIdx.size()) ||
                genIdx >= static_cast<int>(genMotherPdgId.size())) {
                return false;
            }
            return genMotherIdx[genIdx] != -1 && std::abs(genMotherPdgId[genIdx]) == std::abs(requiredMotherPdgId);
        }

        bool PassMuonGenMotherMatch(
            const RVec<int>& muGenMatchIdx,
            const RVec<int>& muGenMatchSource,
            const RVec<int>& genMotherIdx,
            const RVec<int>& genMotherPdgId,
            int muIdx,
            int requiredMotherPdgId
        ) {
            if (muIdx < 0 || muIdx >= static_cast<int>(muGenMatchIdx.size()) ||
                muIdx >= static_cast<int>(muGenMatchSource.size())) {
                return false;
            }
            return PassGenMotherMatch(
                muGenMatchIdx[muIdx],
                muGenMatchSource[muIdx],
                genMotherIdx,
                genMotherPdgId,
                requiredMotherPdgId
            );
        }

        bool PassCandidateTrackGenMotherMatch(
            const RVec<int>& trackGenMatchIdx,
            const RVec<int>& trackGenMatchSource,
            const RVec<int>& genMotherIdx,
            const RVec<int>& genMotherPdgId,
            int candIdx,
            int requiredMotherPdgId
        ) {
            if (candIdx < 0 || candIdx >= static_cast<int>(trackGenMatchIdx.size()) ||
                candIdx >= static_cast<int>(trackGenMatchSource.size())) {
                return false;
            }
            return PassGenMotherMatch(
                trackGenMatchIdx[candIdx],
                trackGenMatchSource[candIdx],
                genMotherIdx,
                genMotherPdgId,
                requiredMotherPdgId
            );
        }

        bool PassSelectedJJPGenMatch(
            int jpsi1_mu1_idx,
            int jpsi1_mu2_idx,
            int jpsi2_mu1_idx,
            int jpsi2_mu2_idx,
            int candIdx,
            const RVec<int>& muGenMatchIdx,
            const RVec<int>& muGenMatchSource,
            const RVec<int>& phiK1GenMatchIdx,
            const RVec<int>& phiK1GenMatchSource,
            const RVec<int>& phiK2GenMatchIdx,
            const RVec<int>& phiK2GenMatchSource,
            const RVec<int>& genMotherIdx,
            const RVec<int>& genMotherPdgId
        ) {
            constexpr int JPSI_PDG_ID = 443;
            constexpr int PHI_PDG_ID = 333;
            return
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, jpsi1_mu1_idx, JPSI_PDG_ID) &&
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, jpsi1_mu2_idx, JPSI_PDG_ID) &&
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, jpsi2_mu1_idx, JPSI_PDG_ID) &&
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, jpsi2_mu2_idx, JPSI_PDG_ID) &&
                PassCandidateTrackGenMotherMatch(phiK1GenMatchIdx, phiK1GenMatchSource, genMotherIdx, genMotherPdgId, candIdx, PHI_PDG_ID) &&
                PassCandidateTrackGenMotherMatch(phiK2GenMatchIdx, phiK2GenMatchSource, genMotherIdx, genMotherPdgId, candIdx, PHI_PDG_ID);
        }

        bool PassSelectedJUPGenMatch(
            int jpsi_mu1_idx,
            int jpsi_mu2_idx,
            int ups_mu1_idx,
            int ups_mu2_idx,
            int candIdx,
            const RVec<int>& muGenMatchIdx,
            const RVec<int>& muGenMatchSource,
            const RVec<int>& phiK1GenMatchIdx,
            const RVec<int>& phiK1GenMatchSource,
            const RVec<int>& phiK2GenMatchIdx,
            const RVec<int>& phiK2GenMatchSource,
            const RVec<int>& genMotherIdx,
            const RVec<int>& genMotherPdgId
        ) {
            constexpr int JPSI_PDG_ID = 443;
            constexpr int UPSILON_PDG_ID = 553;
            constexpr int PHI_PDG_ID = 333;
            return
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, jpsi_mu1_idx, JPSI_PDG_ID) &&
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, jpsi_mu2_idx, JPSI_PDG_ID) &&
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, ups_mu1_idx, UPSILON_PDG_ID) &&
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, ups_mu2_idx, UPSILON_PDG_ID) &&
                PassCandidateTrackGenMotherMatch(phiK1GenMatchIdx, phiK1GenMatchSource, genMotherIdx, genMotherPdgId, candIdx, PHI_PDG_ID) &&
                PassCandidateTrackGenMotherMatch(phiK2GenMatchIdx, phiK2GenMatchSource, genMotherIdx, genMotherPdgId, candIdx, PHI_PDG_ID);
        }

        bool PassSelectedJJYGenMatch(
            int jpsi1_mu1_idx,
            int jpsi1_mu2_idx,
            int jpsi2_mu1_idx,
            int jpsi2_mu2_idx,
            int ups_mu1_idx,
            int ups_mu2_idx,
            const RVec<int>& muGenMatchIdx,
            const RVec<int>& muGenMatchSource,
            const RVec<int>& genMotherIdx,
            const RVec<int>& genMotherPdgId
        ) {
            constexpr int JPSI_PDG_ID = 443;
            constexpr int UPSILON_PDG_ID = 553;
            return
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, jpsi1_mu1_idx, JPSI_PDG_ID) &&
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, jpsi1_mu2_idx, JPSI_PDG_ID) &&
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, jpsi2_mu1_idx, JPSI_PDG_ID) &&
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, jpsi2_mu2_idx, JPSI_PDG_ID) &&
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, ups_mu1_idx, UPSILON_PDG_ID) &&
                PassMuonGenMotherMatch(muGenMatchIdx, muGenMatchSource, genMotherIdx, genMotherPdgId, ups_mu2_idx, UPSILON_PDG_ID);
        }

        bool AllMuonIndicesDistinct(int a, int b, int c, int d, int e, int f) {
            const int values[6] = {a, b, c, d, e, f};
            for (int i = 0; i < 6; ++i) {
                if (values[i] < 0) return false;
                for (int j = i + 1; j < 6; ++j) {
                    if (values[i] == values[j]) return false;
                }
            }
            return true;
        }

        bool AllSelectedMuonSameVertex(
            const RVec<int>& muVertexId,
            int a,
            int b,
            int c,
            int d,
            int e,
            int f
        ) {
            const int values[6] = {a, b, c, d, e, f};
            if (!AllMuonIndicesDistinct(a, b, c, d, e, f)) return false;
            int vertex_id = -1;
            for (int i = 0; i < 6; ++i) {
                const int idx = values[i];
                if (idx >= static_cast<int>(muVertexId.size())) return false;
                const int current = muVertexId[idx];
                if (current < 0) return false;
                if (i == 0) {
                    vertex_id = current;
                } else if (current != vertex_id) {
                    return false;
                }
            }
            return true;
        }

        double Score3(double pt1, double pt2, double pt3) {
            return std::sqrt(pt1 * pt1 + pt2 * pt2 + pt3 * pt3);
        }

        int BestCandIndexJJP(
            const RVec<float>& jpsi1_mass,
            const RVec<float>& jpsi1_pt,
            const RVec<float>& jpsi1_eta,
            const RVec<float>& jpsi1_mu1_idx,
            const RVec<float>& jpsi1_mu2_idx,
            const RVec<float>& jpsi2_mass,
            const RVec<float>& jpsi2_pt,
            const RVec<float>& jpsi2_eta,
            const RVec<float>& jpsi2_mu1_idx,
            const RVec<float>& jpsi2_mu2_idx,
            const RVec<float>& phi_mass,
            const RVec<float>& phi_pt,
            const RVec<float>& phi_eta,
            const RVec<float>& phi_k1_pt,
            const RVec<float>& phi_k1_eta,
            const RVec<float>& phi_k2_pt,
            const RVec<float>& phi_k2_eta,
            const RVec<float>& muPx,
            const RVec<float>& muPy,
            const RVec<float>& muPz,
            const RVec<int>& muIdMask
        ) {
            int best_idx = -1;
            double best_score = -1.;
            const int n_cand = static_cast<int>(jpsi1_mass.size());
            for (int i = 0; i < n_cand; ++i) {
                if (i >= static_cast<int>(jpsi2_mass.size()) || i >= static_cast<int>(phi_mass.size()) ||
                    i >= static_cast<int>(jpsi1_pt.size())   || i >= static_cast<int>(jpsi2_pt.size())   ||
                    i >= static_cast<int>(phi_pt.size())     || i >= static_cast<int>(jpsi1_eta.size())  ||
                    i >= static_cast<int>(jpsi2_eta.size())  || i >= static_cast<int>(phi_eta.size())    ||
                    i >= static_cast<int>(jpsi1_mu1_idx.size()) || i >= static_cast<int>(jpsi1_mu2_idx.size()) ||
                    i >= static_cast<int>(jpsi2_mu1_idx.size()) || i >= static_cast<int>(jpsi2_mu2_idx.size()) ||
                    i >= static_cast<int>(phi_k1_pt.size()) || i >= static_cast<int>(phi_k1_eta.size()) ||
                    i >= static_cast<int>(phi_k2_pt.size()) || i >= static_cast<int>(phi_k2_eta.size())) {
                    continue;
                }

                if (jpsi1_mass[i] < 2.9f || jpsi1_mass[i] > 3.3f) continue;
                if (jpsi2_mass[i] < 2.9f || jpsi2_mass[i] > 3.3f) continue;
                if (phi_mass[i]   < 0.99f || phi_mass[i]   > 1.07f) continue;
                if (jpsi1_pt[i] <= 6.f || jpsi2_pt[i] <= 6.f || phi_pt[i] <= 4.f) continue;
                if (std::fabs(RapidityFromPtEtaM(jpsi1_pt[i], jpsi1_eta[i], jpsi1_mass[i])) >= 2.5f) continue;
                if (std::fabs(RapidityFromPtEtaM(jpsi2_pt[i], jpsi2_eta[i], jpsi2_mass[i])) >= 2.5f) continue;
                if (std::fabs(phi_eta[i]) >= 2.5f) continue;
                if (phi_k1_pt[i] <= 2.f || phi_k2_pt[i] <= 2.f) continue;
                if (std::fabs(phi_k1_eta[i]) >= 2.5f || std::fabs(phi_k2_eta[i]) >= 2.5f) continue;

                const int mu11 = static_cast<int>(jpsi1_mu1_idx[i]);
                const int mu12 = static_cast<int>(jpsi1_mu2_idx[i]);
                const int mu21 = static_cast<int>(jpsi2_mu1_idx[i]);
                const int mu22 = static_cast<int>(jpsi2_mu2_idx[i]);
                if (!PassMuonSelection(muPx, muPy, muPz, muIdMask, mu11)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, muIdMask, mu12)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, muIdMask, mu21)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, muIdMask, mu22)) continue;

                const double score = Score3(jpsi1_pt[i], jpsi2_pt[i], phi_pt[i]);
                if (score > best_score) {
                    best_score = score;
                    best_idx = i;
                }
            }
            return best_idx;
        }

        int BestCandIndexJUP(
            const RVec<float>& jpsi_mass,
            const RVec<float>& jpsi_pt,
            const RVec<float>& jpsi_eta,
            const RVec<float>& jpsi_mu1_idx,
            const RVec<float>& jpsi_mu2_idx,
            const RVec<float>& ups_mass,
            const RVec<float>& ups_pt,
            const RVec<float>& ups_eta,
            const RVec<float>& ups_mu1_idx,
            const RVec<float>& ups_mu2_idx,
            const RVec<float>& phi_mass,
            const RVec<float>& phi_pt,
            const RVec<float>& phi_eta,
            const RVec<float>& phi_k1_pt,
            const RVec<float>& phi_k1_eta,
            const RVec<float>& phi_k2_pt,
            const RVec<float>& phi_k2_eta,
            const RVec<float>& muPx,
            const RVec<float>& muPy,
            const RVec<float>& muPz,
            const RVec<int>& jpsiIdMask,
            const RVec<int>& upsIdMask
        ) {
            int best_idx = -1;
            double best_score = -1.;
            const int n_cand = static_cast<int>(jpsi_mass.size());
            for (int i = 0; i < n_cand; ++i) {
                if (i >= static_cast<int>(ups_mass.size()) || i >= static_cast<int>(phi_mass.size()) ||
                    i >= static_cast<int>(jpsi_pt.size()) || i >= static_cast<int>(ups_pt.size()) ||
                    i >= static_cast<int>(phi_pt.size()) || i >= static_cast<int>(jpsi_eta.size()) ||
                    i >= static_cast<int>(ups_eta.size()) || i >= static_cast<int>(phi_eta.size()) ||
                    i >= static_cast<int>(jpsi_mu1_idx.size()) || i >= static_cast<int>(jpsi_mu2_idx.size()) ||
                    i >= static_cast<int>(ups_mu1_idx.size())  || i >= static_cast<int>(ups_mu2_idx.size())  ||
                    i >= static_cast<int>(phi_k1_pt.size()) || i >= static_cast<int>(phi_k1_eta.size()) ||
                    i >= static_cast<int>(phi_k2_pt.size()) || i >= static_cast<int>(phi_k2_eta.size())) {
                    continue;
                }

                if (jpsi_mass[i] < 2.9f || jpsi_mass[i] > 3.3f) continue;
                if (ups_mass[i]  < 8.5f || ups_mass[i]  > 11.4f) continue;
                if (phi_mass[i]  < 0.99f || phi_mass[i] > 1.07f) continue;
                if (jpsi_pt[i] <= 6.f || phi_pt[i] <= 4.f) continue;
                if (std::fabs(RapidityFromPtEtaM(jpsi_pt[i], jpsi_eta[i], jpsi_mass[i])) >= 2.5f) continue;
                if (std::fabs(RapidityFromPtEtaM(ups_pt[i], ups_eta[i], ups_mass[i])) >= 2.5f) continue;
                if (std::fabs(phi_eta[i]) >= 2.5f) continue;
                if (phi_k1_pt[i] <= 2.f || phi_k2_pt[i] <= 2.f) continue;
                if (std::fabs(phi_k1_eta[i]) >= 2.5f || std::fabs(phi_k2_eta[i]) >= 2.5f) continue;

                const int jmu1 = static_cast<int>(jpsi_mu1_idx[i]);
                const int jmu2 = static_cast<int>(jpsi_mu2_idx[i]);
                const int umu1 = static_cast<int>(ups_mu1_idx[i]);
                const int umu2 = static_cast<int>(ups_mu2_idx[i]);
                if (!PassMuonSelection(muPx, muPy, muPz, jpsiIdMask, jmu1)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, jpsiIdMask, jmu2)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, upsIdMask, umu1)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, upsIdMask, umu2)) continue;

                const double score = Score3(jpsi_pt[i], ups_pt[i], phi_pt[i]);
                if (score > best_score) {
                    best_score = score;
                    best_idx = i;
                }
            }
            return best_idx;
        }

        int BestCandIndexJJY(
            const RVec<float>& jpsi1_mass,
            const RVec<float>& jpsi1_pt,
            const RVec<float>& jpsi1_eta,
            const RVec<float>& jpsi1_mu1_idx,
            const RVec<float>& jpsi1_mu2_idx,
            const RVec<float>& jpsi2_mass,
            const RVec<float>& jpsi2_pt,
            const RVec<float>& jpsi2_eta,
            const RVec<float>& jpsi2_mu1_idx,
            const RVec<float>& jpsi2_mu2_idx,
            const RVec<float>& ups_mass,
            const RVec<float>& ups_pt,
            const RVec<float>& ups_eta,
            const RVec<float>& ups_mu1_idx,
            const RVec<float>& ups_mu2_idx,
            const RVec<float>& muPx,
            const RVec<float>& muPy,
            const RVec<float>& muPz,
            const RVec<int>& jpsiIdMask,
            const RVec<int>& upsIdMask
        ) {
            int best_idx = -1;
            double best_score = -1.;
            const int n_cand = static_cast<int>(jpsi1_mass.size());
            for (int i = 0; i < n_cand; ++i) {
                if (i >= static_cast<int>(jpsi2_mass.size()) || i >= static_cast<int>(ups_mass.size()) ||
                    i >= static_cast<int>(jpsi1_pt.size()) || i >= static_cast<int>(jpsi2_pt.size()) ||
                    i >= static_cast<int>(ups_pt.size()) || i >= static_cast<int>(jpsi1_eta.size()) ||
                    i >= static_cast<int>(jpsi2_eta.size()) || i >= static_cast<int>(ups_eta.size()) ||
                    i >= static_cast<int>(jpsi1_mu1_idx.size()) || i >= static_cast<int>(jpsi1_mu2_idx.size()) ||
                    i >= static_cast<int>(jpsi2_mu1_idx.size()) || i >= static_cast<int>(jpsi2_mu2_idx.size()) ||
                    i >= static_cast<int>(ups_mu1_idx.size()) || i >= static_cast<int>(ups_mu2_idx.size())) {
                    continue;
                }

                if (jpsi1_mass[i] < 2.9f || jpsi1_mass[i] > 3.3f) continue;
                if (jpsi2_mass[i] < 2.9f || jpsi2_mass[i] > 3.3f) continue;
                if (ups_mass[i] < 8.5f || ups_mass[i] > 11.4f) continue;
                if (jpsi1_pt[i] <= 3.f || jpsi2_pt[i] <= 3.f || ups_pt[i] <= 4.f) continue;
                if (std::fabs(RapidityFromPtEtaM(jpsi1_pt[i], jpsi1_eta[i], jpsi1_mass[i])) >= 2.5f) continue;
                if (std::fabs(RapidityFromPtEtaM(jpsi2_pt[i], jpsi2_eta[i], jpsi2_mass[i])) >= 2.5f) continue;
                if (std::fabs(RapidityFromPtEtaM(ups_pt[i], ups_eta[i], ups_mass[i])) >= 2.5f) continue;

                const int mu11 = static_cast<int>(jpsi1_mu1_idx[i]);
                const int mu12 = static_cast<int>(jpsi1_mu2_idx[i]);
                const int mu21 = static_cast<int>(jpsi2_mu1_idx[i]);
                const int mu22 = static_cast<int>(jpsi2_mu2_idx[i]);
                const int umu1 = static_cast<int>(ups_mu1_idx[i]);
                const int umu2 = static_cast<int>(ups_mu2_idx[i]);
                if (!AllMuonIndicesDistinct(mu11, mu12, mu21, mu22, umu1, umu2)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, jpsiIdMask, mu11)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, jpsiIdMask, mu12)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, jpsiIdMask, mu21)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, jpsiIdMask, mu22)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, upsIdMask, umu1)) continue;
                if (!PassMuonSelection(muPx, muPy, muPz, upsIdMask, umu2)) continue;

                const double score = Score3(jpsi1_pt[i], jpsi2_pt[i], ups_pt[i]);
                if (score > best_score) {
                    best_score = score;
                    best_idx = i;
                }
            }
            return best_idx;
        }

        double InvariantMass2(
            float pt1, float eta1, float phi1, float m1,
            float pt2, float eta2, float phi2, float m2
        ) {
            const double px1 = pt1 * std::cos(phi1);
            const double py1 = pt1 * std::sin(phi1);
            const double pz1 = pt1 * std::sinh(eta1);
            const double e1 = std::sqrt(px1 * px1 + py1 * py1 + pz1 * pz1 + m1 * m1);
            const double px2 = pt2 * std::cos(phi2);
            const double py2 = pt2 * std::sin(phi2);
            const double pz2 = pt2 * std::sinh(eta2);
            const double e2 = std::sqrt(px2 * px2 + py2 * py2 + pz2 * pz2 + m2 * m2);
            const double e = e1 + e2;
            const double px = px1 + px2;
            const double py = py1 + py2;
            const double pz = pz1 + pz2;
            const double mass2 = e * e - px * px - py * py - pz * pz;
            return std::sqrt(std::max(0.0, mass2));
        }

        double InvariantMass3(
            float pt1, float eta1, float phi1, float m1,
            float pt2, float eta2, float phi2, float m2,
            float pt3, float eta3, float phi3, float m3
        ) {
            const double px1 = pt1 * std::cos(phi1);
            const double py1 = pt1 * std::sin(phi1);
            const double pz1 = pt1 * std::sinh(eta1);
            const double e1 = std::sqrt(px1 * px1 + py1 * py1 + pz1 * pz1 + m1 * m1);
            const double px2 = pt2 * std::cos(phi2);
            const double py2 = pt2 * std::sin(phi2);
            const double pz2 = pt2 * std::sinh(eta2);
            const double e2 = std::sqrt(px2 * px2 + py2 * py2 + pz2 * pz2 + m2 * m2);
            const double px3 = pt3 * std::cos(phi3);
            const double py3 = pt3 * std::sin(phi3);
            const double pz3 = pt3 * std::sinh(eta3);
            const double e3 = std::sqrt(px3 * px3 + py3 * py3 + pz3 * pz3 + m3 * m3);
            const double e = e1 + e2 + e3;
            const double px = px1 + px2 + px3;
            const double py = py1 + py2 + py3;
            const double pz = pz1 + pz2 + pz3;
            const double mass2 = e * e - px * px - py * py - pz * pz;
            return std::sqrt(std::max(0.0, mass2));
        }
        """
    )
    _RDF_HELPERS_DECLARED = True


def define_selected_columns(rdf, schema: DatasetSchema):
    cfg = CHANNEL_CONFIGS[schema.channel]
    for out_name, in_name in schema.selected_branch_map:
        target = f"sel_{out_name}"
        if out_name.endswith("_Idx"):
            rdf = rdf.Define(target, f"TakeAtInt({in_name}, bestCandIdx)")
        else:
            rdf = rdf.Define(target, f"TakeAt({in_name}, bestCandIdx)")

    for idx_branch, prefix in schema.selected_muon_specs:
        rdf = rdf.Define(f"{prefix}_px", f"TakeAt(muPx, sel_{idx_branch})")
        rdf = rdf.Define(f"{prefix}_py", f"TakeAt(muPy, sel_{idx_branch})")
        rdf = rdf.Define(f"{prefix}_pz", f"TakeAt(muPz, sel_{idx_branch})")
        rdf = rdf.Define(f"{prefix}_pt", f"PtFromPxPy({prefix}_px, {prefix}_py)")
        rdf = rdf.Define(f"{prefix}_eta", f"EtaFromPxyz({prefix}_px, {prefix}_py, {prefix}_pz)")
        rdf = rdf.Define(f"{prefix}_phi", f"PhiFromPxPy({prefix}_px, {prefix}_py)")

    for prefix in schema.selected_particle_prefixes:
        rdf = rdf.Define(f"{prefix}_y", f"RapidityFromPtEtaM({prefix}_pt, {prefix}_eta, {prefix}_mass)")

    for _, left, right in cfg.pair_specs:
        name = _
        rdf = rdf.Define(f"sel_abs_dy_{name}", f"std::fabs({left}_y - {right}_y)")
        rdf = rdf.Define(f"sel_abs_dphi_{name}", f"DeltaPhiAbs({left}_phi, {right}_phi)")
        rdf = rdf.Define(
            f"sel_m_{name}",
            f"InvariantMass2({left}_pt, {left}_eta, {left}_phi, {left}_mass, "
            f"{right}_pt, {right}_eta, {right}_phi, {right}_mass)",
        )

    if schema.channel == "JJP":
        rdf = rdf.Define(
            "sel_m_all",
            "InvariantMass3(sel_Jpsi_1_pt, sel_Jpsi_1_eta, sel_Jpsi_1_phi, sel_Jpsi_1_mass, "
            "sel_Jpsi_2_pt, sel_Jpsi_2_eta, sel_Jpsi_2_phi, sel_Jpsi_2_mass, "
            "sel_Phi_pt, sel_Phi_eta, sel_Phi_phi, sel_Phi_mass)",
        )
    elif schema.channel == "JUP":
        rdf = rdf.Define(
            "sel_m_all",
            "InvariantMass3(sel_Jpsi_pt, sel_Jpsi_eta, sel_Jpsi_phi, sel_Jpsi_mass, "
            "sel_Ups_pt, sel_Ups_eta, sel_Ups_phi, sel_Ups_mass, "
            "sel_Phi_pt, sel_Phi_eta, sel_Phi_phi, sel_Phi_mass)",
        )
    else:
        rdf = rdf.Define(
            "sel_m_all",
            "InvariantMass3(sel_Jpsi_1_pt, sel_Jpsi_1_eta, sel_Jpsi_1_phi, sel_Jpsi_1_mass, "
            "sel_Jpsi_2_pt, sel_Jpsi_2_eta, sel_Jpsi_2_phi, sel_Jpsi_2_mass, "
            "sel_Ups_pt, sel_Ups_eta, sel_Ups_phi, sel_Ups_mass)",
        )
        rdf = rdf.Define(
            "sel_same_mu_vertex",
            "AllSelectedMuonSameVertex(muVertexId, "
            "sel_Jpsi_1_mu_1_Idx, sel_Jpsi_1_mu_2_Idx, "
            "sel_Jpsi_2_mu_1_Idx, sel_Jpsi_2_mu_2_Idx, "
            "sel_Ups_mu_1_Idx, sel_Ups_mu_2_Idx)",
        )
        rdf = rdf.Define("sel_pri_valid", "static_cast<int>(sel_Pri_fitValid) != 0")
        rdf = rdf.Define("sel_pri_vtxprob_gt_0p005", "sel_Pri_VtxProb > 0.005")

    return rdf


def selected_extra_columns(schema: DatasetSchema) -> List[str]:
    cfg = CHANNEL_CONFIGS[schema.channel]
    extra: List[str] = ["bestCandIdx"]
    extra.extend(f"sel_{out_name}" for out_name, _ in schema.selected_branch_map)
    for _, prefix in schema.selected_muon_specs:
        extra.extend(
            [
                f"{prefix}_px",
                f"{prefix}_py",
                f"{prefix}_pz",
                f"{prefix}_pt",
                f"{prefix}_eta",
                f"{prefix}_phi",
            ]
        )
    for prefix in schema.selected_particle_prefixes:
        extra.append(f"{prefix}_y")
    for name, _, _ in cfg.pair_specs:
        extra.extend([f"sel_abs_dy_{name}", f"sel_abs_dphi_{name}", f"sel_m_{name}"])
    extra.append("sel_m_all")
    if schema.channel == "JJY":
        extra.extend(["sel_same_mu_vertex", "sel_pri_valid", "sel_pri_vtxprob_gt_0p005"])
    return extra
