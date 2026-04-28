#!/bin/bash
# Run J/psi + J/psi + Upsilon(1S) MC ntuple analysis.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MAX_EVENTS=-1
JPSI_MUON_ID="soft"
UPS_MUON_ID="tight"
MODE="DPS_1"
DPS_1_DIR="/eos/user/c/chiw/JpsiJpsiUps/MC_samples/rootNtuple_refactor/DPS-Jpsi-JpsiY/filter_JpsiPtMin4p0_YPtMin6p0/"
DPS_2_DIR="/eos/user/c/chiw/JpsiJpsiUps/MC_samples/rootNtuple_refactor/DPS-JpsiJpsi-Y/filter_JpsiPtMin4p0_YPtMin6p0/"
INPUT_DIR=""
INPUT_DIR_OVERRIDE=false
OUTPUT=""
JOBS=1
SAMPLE=""
JPSI_MASS_BINS=40
JPSI_MASS_MIN=2.8
JPSI_MASS_MAX=3.4
UPS_MASS_BINS=60
UPS_MASS_MIN=8.5
UPS_MASS_MAX=10.5

print_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -m, --mode MODE         MC mode: DPS_1 or DPS_2"
    echo "  -i, --input-dir DIR     Input ntuple directory"
    echo "  -n, --max-events N      Maximum events to process (-1=all)"
    echo "  --jpsi-muon-id TYPE     J/psi muon ID (soft/medium/tight/loose/none)"
    echo "  --ups-muon-id TYPE      Upsilon muon ID (tight/medium/loose/soft/none)"
    echo "  -o, --output FILE       Output ROOT file"
    echo "  -j, --jobs N            Parallel processes"
    echo "  --sample NAME           Output sample label"
    echo "  --jpsi-mass-bins N      J/psi m(mumu) bins"
    echo "  --jpsi-mass-min X       J/psi m(mumu) lower edge [GeV]"
    echo "  --jpsi-mass-max X       J/psi m(mumu) upper edge [GeV]"
    echo "  --ups-mass-bins N       Upsilon m(mumu) bins"
    echo "  --ups-mass-min X        Upsilon m(mumu) lower edge [GeV]"
    echo "  --ups-mass-max X        Upsilon m(mumu) upper edge [GeV]"
    echo "  -h, --help              Show this help"
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--mode)
            MODE="$2"; shift 2;;
        -i|--input-dir)
            INPUT_DIR="$2"; INPUT_DIR_OVERRIDE=true; shift 2;;
        -n|--max-events)
            MAX_EVENTS="$2"; shift 2;;
        --jpsi-muon-id)
            JPSI_MUON_ID="$2"; shift 2;;
        --ups-muon-id)
            UPS_MUON_ID="$2"; shift 2;;
        -o|--output)
            OUTPUT="$2"; shift 2;;
        -j|--jobs)
            JOBS="$2"; shift 2;;
        --sample)
            SAMPLE="$2"; shift 2;;
        --jpsi-mass-bins)
            JPSI_MASS_BINS="$2"; shift 2;;
        --jpsi-mass-min)
            JPSI_MASS_MIN="$2"; shift 2;;
        --jpsi-mass-max)
            JPSI_MASS_MAX="$2"; shift 2;;
        --ups-mass-bins)
            UPS_MASS_BINS="$2"; shift 2;;
        --ups-mass-min)
            UPS_MASS_MIN="$2"; shift 2;;
        --ups-mass-max)
            UPS_MASS_MAX="$2"; shift 2;;
        -h|--help)
            print_help; exit 0;;
        *)
            echo "Unknown option: $1"; print_help; exit 1;;
    esac
done

MODE_UPPER="$(echo "$MODE" | tr '[:lower:]' '[:upper:]')"
case "$MODE_UPPER" in
    DPS_1)
        DEFAULT_INPUT_DIR="$DPS_1_DIR"
        DEFAULT_SAMPLE="DPS_1"
        ;;
    DPS_2)
        DEFAULT_INPUT_DIR="$DPS_2_DIR"
        DEFAULT_SAMPLE="DPS_2"
        ;;
    DPS|DPS1|DPS2|SPS)
        echo "Invalid JJY MC mode: $MODE"
        echo "Valid modes are DPS_1 and DPS_2. SPS is reserved; bare DPS is not accepted."
        exit 1
        ;;
    *)
        echo "Invalid JJY MC mode: $MODE"
        echo "Valid modes are DPS_1 and DPS_2."
        exit 1
        ;;
esac

if [[ "$INPUT_DIR_OVERRIDE" != true ]]; then
    INPUT_DIR="$DEFAULT_INPUT_DIR"
fi

if [[ -z "$SAMPLE" ]]; then
    SAMPLE="$DEFAULT_SAMPLE"
fi

if [[ -z "$OUTPUT" ]]; then
    mkdir -p output
    OUTPUT="output/jjy_mc_${SAMPLE}_correlations.root"
fi

PLOT_DIR="$(dirname "$OUTPUT")/plots_JJY_MC_${SAMPLE}"

cat <<EOF
==========================================
JJY MC Ntuple Correlation Analysis
==========================================
Input dir: ${INPUT_DIR}
Mode: ${MODE_UPPER}
Max events: ${MAX_EVENTS}
J/psi muon ID: ${JPSI_MUON_ID}
Upsilon muon ID: ${UPS_MUON_ID}
Output: ${OUTPUT}
Plots: ${PLOT_DIR}
Jobs: ${JOBS}
J/psi mass spectrum: ${JPSI_MASS_BINS} bins, [${JPSI_MASS_MIN}, ${JPSI_MASS_MAX}] GeV
Upsilon mass spectrum: ${UPS_MASS_BINS} bins, [${UPS_MASS_MIN}, ${UPS_MASS_MAX}] GeV
==========================================
EOF

echo "Running analysis..."
CMD=(python3 analyze_ntuple_JJY.py -n "$MAX_EVENTS" --jpsi-muon-id "$JPSI_MUON_ID" --ups-muon-id "$UPS_MUON_ID" -i "$INPUT_DIR" -o "$OUTPUT" -j "$JOBS" --jpsi-mass-bins "$JPSI_MASS_BINS" --jpsi-mass-min "$JPSI_MASS_MIN" --jpsi-mass-max "$JPSI_MASS_MAX" --ups-mass-bins "$UPS_MASS_BINS" --ups-mass-min "$UPS_MASS_MIN" --ups-mass-max "$UPS_MASS_MAX")
"${CMD[@]}"
STATUS=$?

if [[ $STATUS -ne 0 ]]; then
    echo "Analysis failed (exit $STATUS)"
    exit $STATUS
fi

echo "Creating plots..."
mkdir -p "$PLOT_DIR"
python3 plot_ntuple_results.py -i "$OUTPUT" -o "$PLOT_DIR" -p JJY
EXIT_PLOT=$?

if [[ $EXIT_PLOT -ne 0 ]]; then
    echo "Plotting failed (exit $EXIT_PLOT)"
    exit $EXIT_PLOT
fi

echo "=========================================="
echo "MC Ntuple analysis complete"
echo "Output histograms: $OUTPUT"
echo "Output plots: $PLOT_DIR/"
echo "=========================================="
