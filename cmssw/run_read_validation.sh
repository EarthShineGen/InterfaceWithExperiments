#!/bin/bash
#
# Generate a small sample in every interesting configuration, read each one
# back with CMSSW, and check that what came out is what went in.
#
#   cd <a scratch directory>
#   source /cvmfs/cms.cern.ch/cmsset_default.sh
#   cd <any CMSSW area>/src && cmsenv && cd -
#   .../InterfaceWithExperiments/cmssw/run_read_validation.sh
#
# Everything used here is a release plugin; nothing has to be compiled, and no
# particular CMSSW package has to be checked out.
#
# EarthShineGen itself lives in its own repository and knows nothing about
# CMSSW; point EARTHSHINEGEN at the executable if it is not in the default
# place.
#
set -u

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GEN=${EARTHSHINEGEN:-${HOME}/EarthAsDM/EarthShineGen/EarthShineGen}
N_EVENTS=${N_EVENTS:-50}

if [ -z "${CMSSW_BASE:-}" ]; then
    echo "ERROR: no CMSSW environment; run cmsenv first" >&2
    exit 1
fi
if [ ! -x "${GEN}" ]; then
    echo "ERROR: EarthShineGen not found at ${GEN}; set EARTHSHINEGEN" >&2
    exit 1
fi

# name : extra EarthShineGen arguments
CASES=(
    "detector_nome:--stage detector --ms_model none"
    "detector_highland:--stage detector --ms_model highland"
    "vertex_stage:--stage vertex"
    "single_topology:--stage detector --hepmc_topology single"
    "no_mother:--stage detector --include_mother 0"
)

status=0
for entry in "${CASES[@]}"; do
    name="${entry%%:*}"
    args="${entry#*:}"
    echo
    echo "=================================================================="
    echo "== ${name}   (${args})"
    echo "=================================================================="

    mkdir -p "${name}" || exit 1
    ( cd "${name}" || exit 1

      # hepmc_version 2 is pinned: MCFileSource reads HepMC 2, while the
      # generator now defaults to 3.
      python3 "${GEN}" --n_events "${N_EVENTS}" --seed 20260907 \
              --output_file ev.lhe --hepmc_file ev.hepmc --hepmc_version 2 \
              --report_file '' --max_trials 2000000 ${args} > gen.log 2>&1
      if [ $? -ne 0 ]; then
          echo "FAIL ${name}: generation"; tail -20 gen.log; exit 1
      fi

      cmsRun "${HERE}/read_hepmc_cfg.py" inputFiles=file:ev.hepmc \
             > cmsrun.log 2>&1
      if [ $? -ne 0 ]; then
          echo "FAIL ${name}: cmsRun"; tail -30 cmsrun.log; exit 1
      fi

      python3 "${HERE}/check_hepmc_roundtrip.py" ev.hepmc hepmc_read.root
    )
    [ $? -ne 0 ] && status=1
done

echo
if [ ${status} -eq 0 ]; then
    echo "all cases passed"
else
    echo "SOME CASES FAILED"
fi
exit ${status}
