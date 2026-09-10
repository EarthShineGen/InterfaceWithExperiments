#!/bin/bash
#
# EarthShineGen through the full CMS chain, in one command:
#
#   generator -> HepMC 3 -> GEN-SIM -> DIGI-RAW -> RECO
#
#   cd <a scratch directory>
#   source /cvmfs/cms.cern.ch/cmsset_default.sh
#   cd <a CMSSW area with cms-sw/cmssw#51842>/src && cmsenv && cd -
#   .../InterfaceWithExperiments/cmssw/run_chain.sh
#
# Unlike run_gensim.sh this one does need a release with `MCFileSource3`
# (cms-sw/cmssw#51842), because it feeds CMSSW the generator's native HepMC 3.
# Everything after GEN-SIM is a stock cmsDriver step.
#
# Conditions: the cosmics MC GlobalTag, not the collision one.  These muons
# cross the detector the way cosmics do, and the reconstruction that follows is
# the cosmic one (`--scenario cosmics`), which is what actually reconstructs a
# track that does not come from the interaction point.
#
# The generator settings are the ones run_gensim.sh explains: ask for muons
# that reach the *inner* detector, both of them, with the hand-off surface
# shortened to 11 m, or most of the sample clips the outside of CMS and there
# is nothing to reconstruct.
#
set -eu

GEN=${EARTHSHINEGEN:-${HOME}/EarthAsDM/EarthShineGen/EarthShineGen}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
N_EVENTS=${N_EVENTS:-20}
MAX_STEPS=${MAX_STEPS:-200000}
COND=${COND:-auto:phase1_2024_cosmics}
ERA=${ERA:-Run3_2024}

if [ -z "${CMSSW_BASE:-}" ]; then
    echo "ERROR: no CMSSW environment; run cmsenv first" >&2
    exit 1
fi
if [ ! -x "${GEN}" ]; then
    echo "ERROR: EarthShineGen not found at ${GEN}; set EARTHSHINEGEN" >&2
    exit 1
fi

echo "### generating ${N_EVENTS} events"
python3 "${GEN}" \
    --n_events "${N_EVENTS}" --seed 20260909 \
    --output_format hepmc --hepmc_version 3 --hepmc_file ev.hepmc3 \
    --report_file '' \
    --require_hit inner_detector --require_both_muons 1 \
    --detector_half_length 11 --max_trials 4000000

echo "### GEN-SIM"
cmsRun "${HERE}/gensim_cfg.py" \
    inputFiles=file:ev.hepmc3 hepmcVersion=3 maxEvents="${N_EVENTS}" \
    maxSteps="${MAX_STEPS}" outputFile=gensim.root

python3 "${HERE}/check_gensim.py" ev.hepmc3 "gensim_numEvent${N_EVENTS}.root"

# From here on nothing is EarthShineGen-specific: the SIM hits are SIM hits.
COMMON="--mc --scenario cosmics --conditions ${COND} --era ${ERA}"
COMMON="${COMMON} --geometry DB:Extended --no_exec -n ${N_EVENTS}"

echo "### DIGI-RAW"
cmsDriver.py digi --step DIGI,L1,DIGI2RAW \
    --filein "file:gensim_numEvent${N_EVENTS}.root" --fileout file:digi.root \
    --eventcontent FEVTDEBUGHLT --datatier GEN-SIM-DIGI-RAW \
    --python_filename digi_cfg.py ${COMMON}
cmsRun digi_cfg.py

echo "### RECO"
cmsDriver.py reco --step RAW2DIGI,L1Reco,RECO \
    --filein file:digi.root --fileout file:reco.root \
    --eventcontent RECOSIM --datatier GEN-SIM-RECO \
    --python_filename reco_cfg.py ${COMMON}
cmsRun reco_cfg.py

python3 "${HERE}/check_reco.py" reco.root

echo "### done"
ls -l "gensim_numEvent${N_EVENTS}.root" digi.root reco.root
