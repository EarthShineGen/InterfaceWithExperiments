#!/usr/bin/env python3
"""Check that CMSSW got back exactly what EarthShineGen wrote.

    cmsRun read_hepmc_cfg.py inputFiles=file:events.hepmc
    python3 check_hepmc_roundtrip.py events.hepmc hepmc_read.root

The interesting comparison is the vertices.  LHE has one vertex per event and
no field to put it in, so lhe.py writes the muon entry points as comment lines
that nothing downstream reads without a purpose-built producer.  In HepMC each
muon carries its own production vertex, and this script asserts that the point
CMSSW ends up holding is the point EarthShineGen wrote.

Two comparisons, because they are not equally strict:

  * against the `HepMCProduct` -- the generator record as CMSSW stores it,
    full double precision, so momenta and vertices must agree exactly;
  * against `reco::GenParticle` -- the collection analyses actually use.  Those
    are persisted as Double32_t, i.e. float on disk, so the tolerance there is
    a part in a million and no tighter.  Vertices come out in cm.

Needs FWLite, so run it inside cmsenv.  Exits non-zero on any mismatch.
"""

import sys

import ROOT
ROOT.gROOT.SetBatch(True)
ROOT.gSystem.Load("libFWCoreFWLite")
ROOT.FWLiteEnabler.enable()
ROOT.gSystem.Load("libDataFormatsHepMCCandidate")

from DataFormats.FWLite import Events, Handle      # noqa: E402

MM_PER_CM = 10.0

# HepMCProduct keeps what the file said, to the bit.
TOL_EXACT_MM = 1e-9
TOL_EXACT_GEV = 1e-9
# reco::GenParticle is float on disk.
TOL_FLOAT_REL = 2e-6


def parse_hepmc(path):
    """Per event: {barcode: (pdg, status, p4, production vertex mm or None)}."""
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
                pending = None
            elif tag == 'V':
                barcode = int(rest[0])
                vertices[barcode] = tuple(float(v) for v in rest[2:5])
                pending = [barcode, int(rest[6]), int(rest[7]), 0]
            elif tag == 'P':
                vertex, n_in, _, seen = pending
                incoming = seen < n_in
                pending[3] += 1
                current[int(rest[0])] = (
                    int(rest[1]), int(rest[7]),
                    tuple(float(v) for v in rest[2:6]),
                    None if incoming else vertices[vertex])
    return events


def _close(a, b, tol, relative=False):
    scale = max(1.0, abs(b)) if relative else 1.0
    return abs(a - b) <= tol * scale


def check_hepmc_product(events, written, failures):
    """The generator record as CMSSW stores it: must match to the bit."""
    handle = Handle('edm::io_v1::HepMCProduct')
    n_events = n_particles = 0

    for i, event in enumerate(events):
        if i >= len(written):
            failures.append('CMSSW has more events than the HepMC file')
            break
        event.getByLabel(('source', 'generator'), handle)
        evt = handle.product().GetEvent()
        expect = written[i]

        if evt.particles_size() != len(expect):
            failures.append('event %d: wrote %d particles, read back %d'
                            % (i + 1, len(expect), evt.particles_size()))
            continue

        for barcode, (pdg, status, p4, vtx) in expect.items():
            particle = evt.barcode_to_particle(barcode)
            if not particle:
                failures.append('event %d: barcode %d is missing'
                                % (i + 1, barcode))
                continue
            n_particles += 1

            if particle.pdg_id() != pdg or particle.status() != status:
                failures.append(
                    'event %d, barcode %d: got pdg %d status %d, wrote %d %d'
                    % (i + 1, barcode, particle.pdg_id(), particle.status(),
                       pdg, status))

            p = particle.momentum()
            for got, want, name in zip((p.px(), p.py(), p.pz(), p.e()), p4,
                                       ('px', 'py', 'pz', 'E')):
                if not _close(got, want, TOL_EXACT_GEV, relative=True):
                    failures.append('event %d, barcode %d: %s is %.17g, '
                                    'wrote %.17g'
                                    % (i + 1, barcode, name, got, want))

            production = particle.production_vertex()
            if vtx is None:
                if production:
                    failures.append('event %d, barcode %d: gained a '
                                    'production vertex' % (i + 1, barcode))
                continue
            if not production:
                failures.append('event %d, barcode %d: lost its production '
                                'vertex' % (i + 1, barcode))
                continue
            position = production.position()
            for got, want, name in zip((position.x(), position.y(),
                                        position.z()), vtx, 'xyz'):
                if not _close(got, want, TOL_EXACT_MM):
                    failures.append(
                        'event %d, barcode %d: production vertex %s is '
                        '%.9f mm, wrote %.9f mm'
                        % (i + 1, barcode, name, got, want))
        n_events += 1

    return n_events, n_particles


def check_gen_particles(events, written, failures):
    """The reco::GenParticle view, at the precision Double32_t leaves."""
    handle = Handle('std::vector<reco::GenParticle>')
    n_compared = 0

    for i, event in enumerate(events):
        if i >= len(written):
            break
        event.getByLabel(('genParticles',), handle)
        particles = handle.product()

        final_read = [p for p in particles if p.status() == 1]
        final_written = [v for v in written[i].values() if v[1] == 1]
        if len(final_read) != len(final_written):
            failures.append('event %d: %d final-state particles in '
                            'genParticles, %d in the file'
                            % (i + 1, len(final_read), len(final_written)))
            continue

        by_pdg = dict((v[0], v) for v in final_written)
        for particle in final_read:
            if particle.pdgId() not in by_pdg:
                failures.append('event %d: genParticles has an unexpected '
                                'pdg %d' % (i + 1, particle.pdgId()))
                continue
            _, _, p4, vtx = by_pdg[particle.pdgId()]
            n_compared += 1

            # The tolerance scales with the magnitude of the vector, not with
            # the component: reco::GenParticle persists (pt, eta, phi, m) as
            # Double32_t, so a nearly vertical TeV muon has its half-GeV px
            # reconstructed from a float phi and is only good to a part in
            # 10^6 of |p|.  That is a property of the reco format, not of
            # anything this file did.
            pmag = max(1.0, sum(v * v for v in p4[:3]) ** 0.5)
            for got, want, name in zip(
                    (particle.px(), particle.py(), particle.pz(),
                     particle.energy()), p4, ('px', 'py', 'pz', 'E')):
                if abs(got - want) > TOL_FLOAT_REL * pmag:
                    failures.append('event %d, pdg %d: genParticle %s is '
                                    '%.9g, wrote %.9g'
                                    % (i + 1, particle.pdgId(), name, got,
                                       want))

            got_vtx = (particle.vx() * MM_PER_CM, particle.vy() * MM_PER_CM,
                       particle.vz() * MM_PER_CM)
            radius = max(1.0, sum(v * v for v in vtx) ** 0.5)
            for got, want, name in zip(got_vtx, vtx, 'xyz'):
                if abs(got - want) > TOL_FLOAT_REL * radius:
                    failures.append(
                        'event %d, pdg %d: genParticle vertex %s is %.6f mm, '
                        'wrote %.6f mm'
                        % (i + 1, particle.pdgId(), name, got, want))

    return n_compared


def main(hepmc_path, root_path):
    written = parse_hepmc(hepmc_path)
    failures = []

    n_events, n_particles = check_hepmc_product(
        Events(root_path), written, failures)
    n_gen = check_gen_particles(Events(root_path), written, failures)

    if n_events != len(written):
        failures.append('read %d events out of %d written'
                        % (n_events, len(written)))

    print('%d events; %d particles compared against the HepMCProduct, '
          '%d final-state muons against genParticles'
          % (n_events, n_particles, n_gen))
    if failures:
        print('\nFAILURES (%d):' % len(failures))
        for line in failures[:20]:
            print('  ' + line)
        return 1
    print('momenta, statuses and per-particle production vertices all '
          'survived the round trip')
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
