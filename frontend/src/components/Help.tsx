export function Help() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <section className="card">
        <h2 style={{ fontSize: '16px', fontWeight: 700, marginBottom: '8px' }}>
          About FuelFlow
        </h2>
        <p style={{ fontSize: '13px', lineHeight: 1.6 }}>
          FuelFlow is a real fuel-station queue management and recommendation platform.
          Unlike conventional apps that show simulated estimates, FuelFlow is built around strict data integrity:
          we never fabricate vehicle counts, simulate queues, or seed pretend stations.
        </p>
      </section>

      <section className="card">
        <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '8px' }}>
          Frequently Asked Questions
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', fontSize: '13px', lineHeight: 1.6 }}>
          <div>
            <strong>1. Why does it say "Live data unavailable" for a station?</strong>
            <p style={{ marginTop: '4px' }}>
              We only show queue counts when a real CCTV or IP camera is actively connected and processing vehicles via the YOLO computer-vision engine.
              If a camera is disconnected or offline, we state "Live data unavailable" rather than displaying misleading numbers.
            </p>
          </div>

          <div>
            <strong>2. How does slot booking work?</strong>
            <p style={{ marginTop: '4px' }}>
              Station operators configure specific time windows (e.g., 15-minute intervals) with a maximum vehicle capacity.
              When you reserve a slot, our database guarantees that the capacity cannot be exceeded.
              Once confirmed, your spot is saved and guaranteed.
            </p>
          </div>

          <div>
            <strong>3. How are recommendations generated?</strong>
            <p style={{ marginTop: '4px' }}>
              Recommendations are computed mathematically using your verified distance from the station (via browser geolocation),
              active pump count, and remaining slot capacity. If live camera data is missing, we clearly disclose that fact.
            </p>
          </div>

          <div>
            <strong>4. What is the difference between Live CCTV and Recorded Video?</strong>
            <p style={{ marginTop: '4px' }}>
              Live CCTV reflects what is actively happening at the station forecourt right now.
              Recorded Video is uploaded clip footage processed with YOLO computer vision, clearly identified as past recorded analysis and never presented as current live status.
            </p>
          </div>

          <div>
            <strong>5. Is my vehicle and location information private?</strong>
            <p style={{ marginTop: '4px' }}>
              Your location is only used locally in your browser to compute distances to registered stations.
              We do not track your movement or store location history.
            </p>
          </div>
        </div>
      </section>

      <section className="card">
        <h3 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
          Need Further Assistance?
        </h3>
        <p style={{ fontSize: '13px' }}>
          Contact your local station operator or check your reservation reference under <strong>My Bookings</strong>.
        </p>
      </section>
    </div>
  );
}
