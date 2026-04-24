// Requires (loaded via CDN in index.html):
//   aws-sdk   https://sdk.amazonaws.com/js/aws-sdk-2.x.x.min.js
//   mqtt.js   https://unpkg.com/mqtt/dist/mqtt.min.js

const mqttClientModule = (() => {
  let client = null;
  const subscribers = {};

  function subscribe(topic, fn) {
    if (!subscribers[topic]) subscribers[topic] = [];
    subscribers[topic].push(fn);
  }

  function publish(topic, payload) {
    if (!client || !client.connected) {
      console.warn("[mqtt] publish attempted while disconnected");
      return false;
    }
    client.publish(topic, JSON.stringify(payload), { qos: 1 });
    return true;
  }

  async function connect() {
    const creds = await _getCognitoCredentials();
    const url   = _signedWssUrl(creds);

    client = mqtt.connect(url, {
      clientId:        "web-" + crypto.randomUUID().slice(0, 8),
      reconnectPeriod: 5000,
      keepalive:       30,
      transformWsUrl:  () => _signedWssUrl(creds),  // re-sign on reconnect
    });

    client.on("connect", () => {
      console.info("[mqtt] connected");
      client.subscribe([
        `device/${CONFIG.deviceId}/telemetry`,
        `device/${CONFIG.deviceId}/status`,
      ], { qos: 1 });
      statusModule.setPending(false);
    });

    client.on("message", (topic, message) => {
      let payload;
      try { payload = JSON.parse(message.toString()); } catch { return; }
      (subscribers[topic] || []).forEach(fn => fn(payload));
    });

    client.on("offline", () => statusModule.setPending(true));
    client.on("error",   e  => console.error("[mqtt] error", e));
  }

  async function _getCognitoCredentials() {
    AWS.config.region = CONFIG.region;
    const cip = new AWS.CognitoIdentity();

    const { IdentityId } = await cip.getId({
      IdentityPoolId: CONFIG.cognitoPoolId,
    }).promise();

    const { Credentials } = await cip.getCredentialsForIdentity({
      IdentityId,
    }).promise();

    return {
      accessKeyId:     Credentials.AccessKeyId,
      secretAccessKey: Credentials.SecretKey,
      sessionToken:    Credentials.SessionToken,
    };
  }

  // Build AWS SigV4-signed WebSocket URL for IoT Core
  // Reference: https://docs.aws.amazon.com/iot/latest/developerguide/protocols.html
  function _signedWssUrl(creds) {
    const now        = new Date();
    const date       = _isoDate(now);
    const datetime   = _isoDateTime(now);
    const host       = CONFIG.iotEndpoint;
    const region     = CONFIG.region;
    const service    = "iotdevicegateway";
    const algorithm  = "AWS4-HMAC-SHA256";
    const credScope  = `${date}/${region}/${service}/aws4_request`;

    const canonicalQs = [
      `X-Amz-Algorithm=${algorithm}`,
      `X-Amz-Credential=${encodeURIComponent(creds.accessKeyId + "/" + credScope)}`,
      `X-Amz-Date=${datetime}`,
      `X-Amz-Expires=86400`,
      `X-Amz-Security-Token=${encodeURIComponent(creds.sessionToken)}`,
      `X-Amz-SignedHeaders=host`,
    ].join("&");

    const canonicalRequest = [
      "GET",
      "/mqtt",
      canonicalQs,
      `host:${host}\n`,
      "host",
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", // SHA256("")
    ].join("\n");

    const stringToSign = [
      algorithm,
      datetime,
      credScope,
      _sha256hex(canonicalRequest),
    ].join("\n");

    const signingKey = _hmacSha256(
      _hmacSha256(
        _hmacSha256(
          _hmacSha256(
            "AWS4" + creds.secretAccessKey,
            date
          ),
          region
        ),
        service
      ),
      "aws4_request"
    );

    const signature = _hmacSha256Hex(signingKey, stringToSign);
    const signedUrl = `wss://${host}/mqtt?${canonicalQs}&X-Amz-Signature=${signature}`;
    return signedUrl;
  }

  // ---- crypto helpers (SubtleCrypto-free, uses AWS SDK internals) ----

  function _isoDate(d) {
    return d.toISOString().slice(0, 10).replace(/-/g, "");
  }

  function _isoDateTime(d) {
    return d.toISOString().replace(/[:-]/g, "").slice(0, 15) + "Z";
  }

  function _sha256hex(msg) {
    return AWS.util.crypto.sha256(msg, "hex");
  }

  function _hmacSha256(key, data) {
    return AWS.util.crypto.hmac(key, data, "buffer", "sha256");
  }

  function _hmacSha256Hex(key, data) {
    return AWS.util.crypto.hmac(key, data, "hex", "sha256");
  }

  return { connect, publish, subscribe };
})();
