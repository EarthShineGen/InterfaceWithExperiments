#!/usr/bin/env python3
"""Check the GEN-SIM produced from an EarthShineGen HepMC file.

    cmsRun gensim_cfg.py inputFiles=file:events.hepmc
    python3 check_gensim.py events.hepmc \\
        earthshinegen_gensim_numEvent20.root

Asserts the two things GEN-SIM has to get right for this signal:

  * GEANT took exactly the two status-1 muons as primaries, and started each of
    them at its own production vertex -- the point where that muon crosses the
    hand-off surface, several metres off the beamline.  Nothing else from the
    record (the mock beams, the dark photon, the muons as produced deep in the
    rock) may appear as a primary; if any of them did, GEANT would be tracking
    a particle from a kilometre underground.

  * the muons were actually propagated: they leave hits in the muon system and,
    since they enter from outside and travel inward, in the tracker as well.

Needs FWLite, so run it inside cmsenv.  Exits non-zero on any mismatch.
"""

import sys

import ROOT
ROOT.gROOT.SetBatch(True)
ROOT.gSystem.Load("libFWCoreFWLite")
ROOT.FWLiteEnabler.enable()
ROOT.gSystem.Load("libSimDataFormatsTrack")

from DataFormats.FWLite import Events, Handle      # noqa: E402

MM_PER_CM = 10.0
TOL_MM = 1e-3          # SimVertex positions are floats, in cm

MUON_HIT_LABELS = ('MuonDTHits', 'MuonCSCHits', 'MuonRPCHits')
TRACKER_HIT_LABELS = ('TrackerHitsTIBLowTof', 'TrackerHitsTOBLowTof',
                      'TrackerHitsTECLowTof', 'TrackerHitsTIDLowTof',
                      'TrackerHitsPixelBarrelLowTof',
                      'TrackerHitsPixelEndcapLowTof')


def parse_final_muons(path):
    """Per event: {pdg: production vertex in mm} for the status-1 particles.

    Reads either HepMC version.  Which one it is is decided by the listing
    marker, not by the `HepMC::Version` line above it: that line carries the
    version of the *library* that wrote the file, so a HepMC 2 file written by
    HepMC3's WriterAsciiHepMC2 announces itself as version 3.03.01.  Both are
    written in mm by the generator.
    """
    with open(path) as fh:
        for _ in range(5):
            line = fh.readline()
            if not line:
                break
            if line.startswith('HepMC::Asciiv3-START_EVENT_LISTING'):
                return parse_final_muons_v3(path)
            if line.startswith('HepMC::IO_GenEvent-START_EVENT_LISTING'):
                return parse_final_muons_v2(path)
    raise SystemExit('%s: no HepMC event listing in the first lines' % path)


def parse_final_muons_v3(path):
    """parse_final_muons for the HepMC 3 ASCII format.

    A particle line carries the id of its production vertex, so unlike in
    HepMC 2 there is no incoming/outgoing bookkeeping to do:

        V -2 0 [3] @ <x> <y> <z> <t>
        P 4 -2 13 <px> <py> <pz> <e> <m> <status>
    """
    events = []
    current = None
    vertices = {}
    listing = False

    with open(path) as fh:
        for raw in fh:
            line = raw.rstrip('\n')
            if line.startswith('HepMC::Asciiv3-START_EVENT_LISTING'):
                listing = True
                continue
            if line.startswith('HepMC::Asciiv3-END_EVENT_LISTING'):
                break
            if not listing or not line:
                continue

            tag, rest = line[0], line[2:].split()
            if tag == 'E':
                current = {}
                vertices = {}
                events.append(current)
            elif tag == 'V':
                # the position is only written if the vertex has one
                if '@' in rest:
                    at = rest.index('@')
                    vertices[int(rest[0])] = tuple(
                        float(v) for v in rest[at + 1:at + 4])
            elif tag == 'P':
                if int(rest[8]) == 1:
                    current[int(rest[2])] = vertices[int(rest[1])]
    return events


def parse_final_muons_v2(path):
    """parse_final_muons for the HepMC 2 ASCII format."""
    events = []
    current = None
    vertices = {}
    listing = False
    pending = None

    with open(path) as fh:
        for raw in fh:
            line = raw.rstrip('\n')
            if line.startswith('HepMC::IO_GenEvent-START_EVENT_LISTING'):
                listing = True
                continue
            if line.startswith('HepMC::IO_GenEvent-END_EVENT_LISTING'):
                break
            if not listing or not line:
                continue

            tag, rest = line[0], line[2:].split()
            if tag == 'E':
                current = {}
                vertices = {}
                events.append(current)
            elif tag == 'V':
                barcode = int(rest[0])
                vertices[barcode] = tuple(float(v) for v in rest[2:5])
                pending = [barcode, int(rest[6]), int(rest[7]), 0]
            elif tag == 'P':
                vertex, n_in, _, seen = pending
                incoming = seen < n_in
                pending[3] += 1
                if int(rest[7]) == 1 and not incoming:
                    current[int(rest[1])] = vertices[vertex]
    return events


def main(hepmc_path, root_path):
    written = parse_final_muons(hepmc_path)
    tracks = Handle('std::vector<io_v1::SimTrack>')
    vertices = Handle('std::vector<io_v1::SimVertex>')
    hits = Handle('std::vector<io_v1::PSimHit>')

    failures = []
    n_events = 0
    n_with_muon_hits = 0
    n_with_tracker_hits = 0

    for i, event in enumerate(Events(root_path)):
        event.getByLabel(('g4SimHits',), tracks)
        event.getByLabel(('g4SimHits',), vertices)
        sim_tracks = tracks.product()
        sim_vertices = vertices.product()
        expect = written[i]
        n_events += 1

        primaries = [t for t in sim_tracks
                     if t.vertIndex() >= 0
                     and sim_vertices[t.vertIndex()].parentIndex() < 0]
        if len(primaries) != len(expect):
            failures.append('event %d: %d primary SimTracks, expected %d'
                            % (i + 1, len(primaries), len(expect)))
            continue

        for track in primaries:
            pdg = track.type()
            if pdg not in expect:
                failures.append('event %d: primary SimTrack with pdg %d was '
                                'not a status-1 particle in the record; GEANT '
                                'is tracking something it should not'
                                % (i + 1, pdg))
                continue
            position = sim_vertices[track.vertIndex()].position()
            got = (position.x() * MM_PER_CM, position.y() * MM_PER_CM,
                   position.z() * MM_PER_CM)
            want = expect[pdg]
            scale = max(1.0, sum(v * v for v in want) ** 0.5)
            for a, b, name in zip(got, want, 'xyz'):
                if abs(a - b) > TOL_MM * scale:
                    failures.append(
                        'event %d, pdg %d: GEANT started the muon at %s = '
                        '%.4f mm, the record says %.4f mm'
                        % (i + 1, pdg, name, a, b))

        muon_hits = 0
        for label in MUON_HIT_LABELS:
            event.getByLabel(('g4SimHits', label), hits)
            muon_hits += hits.product().size()
        tracker_hits = 0
        for label in TRACKER_HIT_LABELS:
            event.getByLabel(('g4SimHits', label), hits)
            tracker_hits += hits.product().size()

        n_with_muon_hits += (muon_hits > 0)
        n_with_tracker_hits += (tracker_hits > 0)

    if n_events == 0:
        failures.append('no events in the GEN-SIM file')
    # Not every event has to reach the chambers: with --require_hit
    # inner_detector a muon may cross the inner cylinder and still stop or exit
    # before any muon station.  Seed 20260907 gave 20 of 20, seed 20260909 gave
    # 17 of 20 -- and identically so from HepMC 2 and HepMC 3 -- so this is a
    # property of the sample, not of the reading path.  Only an empty sample is
    # a failure; the rate is printed either way.
    if n_with_muon_hits == 0:
        failures.append('no event left a hit in the muon system')
    if n_with_tracker_hits == 0:
        failures.append('no event left a tracker hit; the muons did not '
                        'reach the middle of the detector')

    print('%d events; %d with muon-system hits, %d with tracker hits'
          % (n_events, n_with_muon_hits, n_with_tracker_hits))
    if failures:
        print('\nFAILURES (%d):' % len(failures))
        for line in failures[:20]:
            print('  ' + line)
        return 1
    print('GEANT took the two arriving muons as primaries, each at its own '
          'crossing of the hand-off surface, and propagated them into the '
          'detector')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
