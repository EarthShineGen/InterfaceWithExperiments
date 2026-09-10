#!/bin/bash
#
# End-to-end GEN-SIM from EarthShineGen, in one command.
#
#   cd <a scratch directory>
#   source /cvmfs/cms.cern.ch/cmsset_default.sh
#   cd <any CMSSW area>/src && cmsenv && cd -
#   .../InterfaceWithExperiments/cmssw/run_gensim.sh
#
# Nothing has to be compiled: MCFileSource and g4SimHits are release plugins.
#
# About the generator settings below.  EarthShineGen's default acceptance
# requirement, `require_hit detector`, only asks that the muon reach the
# hand-off surface -- which is the detector's own outer cylinder, so it is
# satisfied by definition and most muons clip the outside and travel on up
# without ever entering CMS.  A GEN-SIM sample wants muons that actually cross
# the detector, so this asks for both muons to point at the inner cylinder, and
# shortens the hand-off surface from the generic 15 m half length to 11 m,
# beyond which there is no CMS left to hit.  With those settings 20 out of 20
# events leave hits in the muon system and 18 of 20 in the tracker.  That first
# number is sample dependent -- seed 20260909 gives 17 of 20 -- because
# reaching the inner cylinder does not guarantee reaching a muon station.
#
# This script stays on HepMC 2 so that it runs in any release.  For the
# generator's native HepMC 3, and for the steps after GEN-SIM, use run_chain.sh
# in a release that has MCFileSource3 (cms-sw/cmssw#51842).
#
set -eu

GEN=${EARTHSHINEGEN:-${HOME}/EarthAsDM/EarthShineGen/EarthShineGen}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
N_EVENTS=${N_EVENTS:-20}
# Ten times the release default.  At the default, ~1.5% of these muons run out
# of GEANT steps in the endcap chambers before they run out of detector; this
# removes that for 3.5% more CPU.  See docs/rpc-stepping.md.
MAX_STEPS=${MAX_STEPS:-200000}

if [ -z "${CMSSW_BASE:-}" ]; then
    echo "ERROR: no CMSSW environment; run cmsenv first" >&2
    exit 1
fi
if [ ! -x "${GEN}" ]; then
    echo "ERROR: EarthShineGen not found at ${GEN}; set EARTHSHINEGEN" >&2
    exit 1
fi

python3 "${GEN}" \
    --n_events "${N_EVENTS}" --seed 20260907 \
    --output_format hepmc --hepmc_version 2 --hepmc_file ev.hepmc \
    --report_file '' \
    --require_hit inner_detector --require_both_muons 1 \
    --detector_half_length 11 --max_trials 4000000

cmsRun "${HERE}/gensim_cfg.py" \
    inputFiles=file:ev.hepmc maxEvents="${N_EVENTS}" maxSteps="${MAX_STEPS}"

python3 "${HERE}/check_gensim.py" \
    ev.hepmc "earthshinegen_gensim_numEvent${N_EVENTS}.root"
