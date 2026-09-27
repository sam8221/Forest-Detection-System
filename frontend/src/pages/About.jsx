/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: About Page
 *
 * Purpose:
 *   Describes what the system is, who built it, how it
 *   detects deforestation, and where its imagery comes from.
 *
 * Responsibilities:
 *   - State the system's identity, author and institution.
 *   - Explain the detection method in plain terms.
 *   - Record the thresholds a detection is judged against.
 *   - Report whether the server is currently reachable.
 *
 * How it works:
 *
 *   Most of this page is fixed description. The one live
 *   part is the connection check at the bottom, which calls
 *   the API's unauthenticated health endpoint and reports
 *   what came back.
 *
 *   That check earns its place: when an officer says "the
 *   system is not working", the first question is whether
 *   the browser can reach the server at all, and this
 *   answers it without anyone opening developer tools. It
 *   also shows the API address the interface is actually
 *   using, which is the setting most often wrong after a
 *   deployment.
 *
 *   Note what a successful check does and does not prove. It
 *   confirms the API process is answering. It does not
 *   confirm the database is reachable, that the Copernicus
 *   credentials are valid, or that analysis jobs are being
 *   processed. The wording on the page is careful about that
 *   distinction rather than implying everything is well.
 *
 * Why the method is described here:
 *   Officers act on these detections, and an alert is more
 *   useful to someone who knows what produced it: that the
 *   system compares vegetation index values between two
 *   seasons a year apart, that it ignores anything smaller
 *   than half a hectare, and that it proposes rather than
 *   concludes. A detection is a candidate for a field visit,
 *   not a finding.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 * ===========================================================
 */

import React, { useEffect, useState } from "react";

import {
  AlertTriangle,
  CheckCircle2,
  Globe2,
  Layers,
  Leaf,
  RefreshCw,
  Satellite,
  ShieldCheck,
  TreePine,
} from "lucide-react";

import { API_URL, API_V1 } from "../config";

// =========================================================
// SYSTEM IDENTITY
//
// Held as constants rather than written into the markup so
// the same values can be reused, and so a version change is
// made in one place.
// =========================================================

const SYSTEM = {
  name: "ForestWatch Zambia",
  version: "1.0.0",
  title:
    "Automated Web-Based Deforestation Detection and " +
    "Alert System Using Sentinel-2 Imagery for the " +
    "Copperbelt Province, Zambia",
  author: "Samuel Bikiloni",
  studentNumber: "2300096",
  supervisor: "Mr. Chilanga",
  institution: "Zambia University College of Technology",
  programme: "BSc Information Technology",
};

// =========================================================
// DETECTION RULES
//
// These mirror the server's configured defaults. They are
// shown so an officer can see what a detection was judged
// against rather than having to take the result on trust.
//
// The server is authoritative: an administrator may change a
// threshold, and a job may carry its own. The figures below
// describe the standard configuration.
// =========================================================

const RULES = [
  {
    label: "Minimum detectable area",
    value: "0.5 hectares",
    note:
      "50 Sentinel-2 pixels at 10 m resolution. Taken " +
      "from the area threshold in the Forests Act No. 4 " +
      "of 2015, and suppresses isolated noise pixels.",
  },
  {
    label: "NDVI decline threshold",
    value: "0.30",
    note:
      "How far the vegetation index must fall between the " +
      "two periods before a patch is reported. Adjustable " +
      "per analysis.",
  },
  {
    label: "Maximum cloud cover",
    value: "30%",
    note:
      "Scenes above this are not used. Cloud is masked " +
      "with the Sentinel-2 scene classification band.",
  },
  {
    label: "Satellite revisit",
    value: "~5 days",
    note:
      "How often Sentinel-2 passes over the Copperbelt. " +
      "Cloud, not revisit frequency, is the limiting " +
      "factor in the rainy season.",
  },
];

export default function About() {
  // -------------------------------------------------------
  // CONNECTION CHECK
  // -------------------------------------------------------

  // "checking" until the request settles, then "online" or
  // "offline". Kept as a string rather than a boolean so the
  // first render does not have to claim one or the other.
  const [connection, setConnection] = useState("checking");

  const [checkedAt, setCheckedAt] = useState(null);

  /**
   * Ask the server whether it is answering requests.
   *
   * Uses the unauthenticated health endpoint deliberately:
   * the check should work even when a session has expired,
   * because "am I signed out?" and "is the server down?" are
   * the two things being told apart here.
   *
   * @returns {Promise<void>}
   */
  const checkConnection = async () => {
    setConnection("checking");

    try {
      const response = await fetch(`${API_V1}/health`, {
        method: "GET",
        headers: { Accept: "application/json" },
      });

      setConnection(response.ok ? "online" : "offline");
    } catch {
      // A network-level failure: wrong address, server not
      // running, or no route to it. Indistinguishable from
      // here, and all three mean the same thing to the
      // officer reading this.
      setConnection("offline");
    } finally {
      setCheckedAt(new Date());
    }
  };

  useEffect(() => {
    checkConnection();
  }, []);

  // -------------------------------------------------------
  // RENDER
  // -------------------------------------------------------

  return (
    <div className="forest-page">

      {/* =====================================================
          HEADER
      ====================================================== */}

      <div className="page-header">

        <div>
          <h1>About</h1>

          <p>
            What this system does, how it detects
            deforestation, and who built it.
          </p>
        </div>

      </div>

      {/* =====================================================
          IDENTITY
      ====================================================== */}

      <section className="about-card about-identity">

        <div className="about-identity-mark" aria-hidden="true">
          <TreePine size={30} />
        </div>

        <div className="about-identity-text">

          <h2>{SYSTEM.name}</h2>

          <p className="about-title">
            {SYSTEM.title}
          </p>

          <span className="about-version">
            Version {SYSTEM.version}
          </span>

        </div>

      </section>

      {/* =====================================================
          PURPOSE
      ====================================================== */}

      <section className="about-card">

        <h3>
          <Leaf size={17} aria-hidden="true" />
          Purpose
        </h3>

        <p>
          Forest loss in the Copperbelt is usually noticed
          long after it happens. Ground patrols cannot cover
          the province often enough to find new clearings
          while there is still something to be done about
          them.
        </p>

        <p>
          This system watches the same ground from orbit. It
          compares satellite measurements of vegetation
          across time, identifies places where cover has
          fallen away, and tells the officer responsible for
          that district — so that a clearing is investigated
          in weeks rather than discovered in hindsight.
        </p>

        <p className="about-emphasis">
          The system proposes; it does not conclude. Every
          detection is a candidate for a field visit, and
          stays marked pending until an officer confirms or
          rejects it.
        </p>

      </section>

      {/* =====================================================
          METHOD
      ====================================================== */}

      <section className="about-card">

        <h3>
          <Layers size={17} aria-hidden="true" />
          How detection works
        </h3>

        <ol className="about-steps">

          <li>
            <strong>Imagery is acquired.</strong> Sentinel-2
            products covering a registered forest area are
            downloaded from the Copernicus Data Space
            Ecosystem.
          </li>

          <li>
            <strong>Cloud is removed.</strong> The scene
            classification band marks cloud, shadow and
            water, and those pixels are excluded before
            anything is measured.
          </li>

          <li>
            <strong>Vegetation is measured.</strong> NDVI is
            calculated for every remaining pixel from the
            red and near-infrared bands. Healthy vegetation
            reflects strongly in near-infrared and weakly in
            red, so the index falls when cover is lost.
          </li>

          <li>
            <strong>Two seasons are compared.</strong> The
            same calendar window is measured one year apart
            and the difference taken.
          </li>

          <li>
            <strong>Patches are grouped and filtered.</strong>{" "}
            Adjacent pixels showing decline are joined into
            patches, and any patch under half a hectare is
            discarded as noise.
          </li>

          <li>
            <strong>The officer is alerted.</strong> Each
            surviving patch becomes a detection, and an alert
            is emailed to the officers whose jurisdiction
            covers it.
          </li>

        </ol>

        <div className="about-note">
          <AlertTriangle size={16} aria-hidden="true" />

          <p>
            <strong>Why a year apart, and not last month.</strong>{" "}
            Miombo woodland across the Copperbelt sheds leaf
            every dry season, so vegetation index values fall
            province-wide whether or not any trees were cut.
            Comparing consecutive months would report
            deforestation almost everywhere. Comparing the
            same season in different years removes that
            cycle, leaving change that is genuinely a change
            in cover.
          </p>
        </div>

      </section>

      {/* =====================================================
          THRESHOLDS
      ====================================================== */}

      <section className="about-card">

        <h3>
          <Satellite size={17} aria-hidden="true" />
          What a detection is judged against
        </h3>

        <div className="about-rules">

          {RULES.map((rule) => (
            <div className="about-rule" key={rule.label}>

              <span className="about-rule-value">
                {rule.value}
              </span>

              <span className="about-rule-label">
                {rule.label}
              </span>

              <span className="about-rule-note">
                {rule.note}
              </span>

            </div>
          ))}

        </div>

        {/* The legal basis is quoted rather than paraphrased,
            and what the system does NOT test is stated. The
            Act defines a forest by three criteria; this
            system applies one of them. Implying otherwise
            would overstate what a detection means. */}

        <div className="about-note">
          <ShieldCheck size={16} aria-hidden="true" />

          <div>

            <p>
              <strong>Where the half hectare comes from.</strong>{" "}
              The Forests Act No. 4 of 2015 defines a forest
              as:
            </p>

            <blockquote className="about-quote">
              “any land with a tree canopy cover of more than
              ten percent and area of more than zero point
              five hectares and includes young stands that
              have not yet reached, but are expected to
              reach, a crown density of ten percent and tree
              height of five metres”
            </blockquote>

            <p>
              The system applies the <strong>area</strong>{" "}
              criterion from that definition, so that a patch
              too small to constitute a forest in law is not
              reported. It does not measure canopy cover
              against the ten percent threshold, nor tree
              height, so a detection is not in itself a
              finding that a forest as legally defined has
              been cleared. That determination is the
              officer&rsquo;s, on the ground.
            </p>

          </div>
        </div>

      </section>

      {/* =====================================================
          DATA SOURCE
      ====================================================== */}

      <section className="about-card">

        <h3>
          <Globe2 size={17} aria-hidden="true" />
          Imagery and access
        </h3>

        <dl className="about-facts">

          <div>
            <dt>Imagery source</dt>
            <dd>
              Copernicus Data Space Ecosystem — Sentinel-2
              Level-2A, 10 m resolution, surface reflectance.
            </dd>
          </div>

          <div>
            <dt>Base mapping</dt>
            <dd>
              Esri World Imagery and World Street Map, with
              place names and district boundaries drawn over
              the top.
            </dd>
          </div>

          <div>
            <dt>Study area</dt>
            <dd>
              Copperbelt Province, Zambia. The system is not
              limited to it; the monitored extent is a
              configured setting.
            </dd>
          </div>

          <div>
            <dt>Access</dt>
            <dd>
              Restricted to authorised Forestry Department
              officers, scoped to the district or province
              each account covers.
            </dd>
          </div>

        </dl>

        <div className="about-note">
          <ShieldCheck size={16} aria-hidden="true" />

          <p>
            <strong>Why this system is not public.</strong>{" "}
            It holds the precise locations of suspected
            illegal clearing. Publishing those would inform
            the people responsible, so access is restricted
            by design rather than by convenience, and every
            record is scoped to the officer who is
            accountable for that ground.
          </p>
        </div>

      </section>

      {/* =====================================================
          AUTHORSHIP
      ====================================================== */}

      <section className="about-card">

        <h3>
          <TreePine size={17} aria-hidden="true" />
          Authorship
        </h3>

        <dl className="about-facts">

          <div>
            <dt>Author</dt>
            <dd>
              {SYSTEM.author} ({SYSTEM.studentNumber})
            </dd>
          </div>

          <div>
            <dt>Supervisor</dt>
            <dd>{SYSTEM.supervisor}</dd>
          </div>

          <div>
            <dt>Institution</dt>
            <dd>{SYSTEM.institution}</dd>
          </div>

          <div>
            <dt>Programme</dt>
            <dd>
              {SYSTEM.programme} — final-year dissertation
              project.
            </dd>
          </div>

        </dl>

      </section>

      {/* =====================================================
          CONNECTION

          Placed last: it is the part an officer is sent to
          when something is wrong, rather than something they
          read on the way past.
      ====================================================== */}

      <section className="about-card">

        <h3>
          <RefreshCw size={17} aria-hidden="true" />
          Server connection
        </h3>

        <div className="about-connection">

          <span
            className={`about-status about-status--${connection}`}
            role="status"
            aria-live="polite"
          >
            {connection === "online" && (
              <CheckCircle2 size={16} aria-hidden="true" />
            )}

            {connection === "offline" && (
              <AlertTriangle size={16} aria-hidden="true" />
            )}

            {connection === "checking"
              ? "Checking…"
              : connection === "online"
              ? "Server reachable"
              : "Server not reachable"}
          </span>

          <button
            type="button"
            className="refresh-button"
            onClick={checkConnection}
            disabled={connection === "checking"}
          >
            <RefreshCw size={15} aria-hidden="true" />
            Check again
          </button>

        </div>

        <dl className="about-facts">

          <div>
            <dt>API address</dt>
            <dd className="about-mono">{API_URL}</dd>
          </div>

          {checkedAt && (
            <div>
              <dt>Last checked</dt>
              <dd>
                {checkedAt.toLocaleTimeString("en-ZM")}
              </dd>
            </div>
          )}

        </dl>

        {/* Stated plainly, because a green tick that is read
            as "everything works" is worse than no tick. */}
        <p className="about-caveat">
          This confirms the browser can reach the server. It
          does not confirm that the database is available or
          that analysis jobs are running.
        </p>

        {connection === "offline" && (
          <div className="about-note about-note--warn">
            <AlertTriangle size={16} aria-hidden="true" />

            <p>
              The interface cannot reach the server. Check
              that the backend is running, and that the API
              address above is the one it is serving on.
              Detections and alerts already recorded are
              unaffected.
            </p>
          </div>
        )}

      </section>

    </div>
  );
}
