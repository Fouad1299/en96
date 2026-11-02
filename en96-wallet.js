
/*
 EN96 Ice Bear Kingdom
 Stellar WalletConnect - Mobile First

 No seed phrases, private keys or payments.
 Connection does not prove wallet ownership.
 Mining and Telegram registration stay independent.
*/

(function () {
  "use strict";

  const CONFIG = Object.freeze({
    projectId: "3e9fa0461e993b4dbc10fb444a3ca46f",
    projectName: "EN96 Ice Bear Kingdom",
    network: "stellar:pubnet",
    assetCode: "EN96",
    issuer:
      "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB",
    website: "https://fouad1299.github.io/en96/",
    apiBase: "https://en96.onrender.com"
  });

  let client = null;
  let session = null;
  let address = null;
  let connecting = false;

  function make(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  }

  function status(message) {
    const node = document.getElementById("en96WCStatus");
    if (node) node.textContent = message;
  }

  function closeModal() {
    document.getElementById("en96WCOverlay")?.remove();
  }

  function styles() {
    if (document.getElementById("en96WCStyle")) return;

    const sheet = make("style");
    sheet.id = "en96WCStyle";

    sheet.textContent = `
      .en96-wc-main {
        width:100%;
        margin:16px 0;
        padding:17px;
        border:1px solid #ffefb0;
        border-radius:18px;
        color:#4b2300;
        font-size:18px;
        font-weight:900;
        background:linear-gradient(
          135deg,#fff3a1,#ffcb3d,#ffa31c
        );
        cursor:pointer;
      }
      .en96-wc-status {
        margin:12px 0 18px;
        padding:14px;
        background:#29100e;
        border:1px solid #aa8149;
        border-radius:13px;
        color:#ffe3ad;
        font-size:12px;
        line-height:1.8;
        overflow-wrap:anywhere;
        white-space:pre-line;
      }
      .en96-wc-overlay {
        position:fixed;
        inset:0;
        z-index:99999;
        display:flex;
        align-items:center;
        justify-content:center;
        padding:14px;
        background:rgba(0,0,0,.82);
      }
      .en96-wc-modal {
        width:100%;
        max-width:460px;
        max-height:88dvh;
        overflow-y:auto;
        padding:19px;
        border:2px solid #e8b850;
        border-radius:24px;
        background:linear-gradient(
          155deg,#572115,#260b0b
        );
        text-align:center;
        direction:rtl;
        color:#fff;
      }
      .en96-wc-modal h2 {
        color:#ffe39b;
        font-size:22px;
        margin:4px 0 14px;
      }
      .en96-wc-modal p {
        color:#ffe4cb;
        font-size:12px;
        line-height:1.8;
      }
      .en96-wc-action {
        display:block;
        width:100%;
        padding:15px;
        margin-top:12px;
        background:#3c180f;
        border:1px solid #bc9251;
        border-radius:14px;
        color:#fff2d2;
        font-size:15px;
        font-weight:bold;
        text-decoration:none;
        cursor:pointer;
      }
      .en96-wc-action.primary {
        background:linear-gradient(
          135deg,#ffe98c,#ffb627
        );
        color:#402008;
        border-color:#ffeaa3;
      }
      .en96-wc-action:disabled {
        opacity:.5;
        cursor:not-allowed;
      }
      .en96-wc-qr {
        display:block;
        width:min(70vw,270px);
        max-width:100%;
        margin:15px auto;
        padding:10px;
        background:white;
        border-radius:14px;
      }
      .en96-wc-address {
        margin-top:10px;
        padding:12px;
        direction:ltr;
        text-align:left;
        overflow-wrap:anywhere;
        font-size:11px;
        color:#ffdfa0;
      }
    `;

    document.head.appendChild(sheet);
  }

  function button(label, action, primary = false) {
    const node = make(
      "button",
      "en96-wc-action" + (primary ? " primary" : ""),
      label
    );

    node.type = "button";
    node.addEventListener("click", action);
    return node;
  }

  function dialog(title, description) {
    closeModal();

    const overlay = make("div", "en96-wc-overlay");
    overlay.id = "en96WCOverlay";

    const modal = make("div", "en96-wc-modal");
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");

    modal.append(
      make("h2", "", title),
      make("p", "", description)
    );

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    overlay.addEventListener("click", event => {
      if (event.target === overlay) closeModal();
    });

    return modal;
  }

  function closeButton(modal) {
    modal.appendChild(
      button("✕ إغلاق", closeModal)
    );
  }

  async function getClient() {
    if (client) return client;

    const sdk = await import(
      "https://esm.sh/@walletconnect/sign-client@2.26.0?bundle"
    );

    const SignClient = sdk.default || sdk.SignClient;

    if (!SignClient?.init) {
      throw new Error(
        "تعذر تحميل مكتبة WalletConnect."
      );
    }

    client = await SignClient.init({
      projectId: CONFIG.projectId,
      metadata: {
        name: CONFIG.projectName,
        description: "EN96 Stellar wallet connection",
        url: CONFIG.website,
        icons: [
          CONFIG.website + "en96-coin.webp"
        ]
      }
    });

    client.on("session_delete", () => {
      session = null;
      address = null;
      status("🔒 تم قطع اتصال المحفظة.");
      showAddress();
    });

    return client;
  }

  function showAddress() {
    const node = document.getElementById("en96WCAddress");

    if (node) {
      node.textContent = address
        ? "Stellar: " + address
        : "";
    }
  }

  function getStellarAddress(currentSession) {
    const accounts =
      currentSession?.namespaces?.stellar?.accounts || [];

    const prefix = CONFIG.network + ":";

    const account = accounts.find(
      value =>
        typeof value === "string" &&
        value.startsWith(prefix)
    );

    const result = account
      ? account.slice(prefix.length)
      : "";

    if (!/^G[A-Z2-7]{55}$/.test(result)) {
      throw new Error(
        "لم تُرجع المحفظة عنوان Stellar صالحًا."
      );
    }

    return result;
  }

  function openWalletChooser() {
    const modal = dialog(
      "👑 Connect Wallet",
      "اربط LOBSTR من هاتف واحد، أو استخدم QR. " +
      "لا نطلب مفاتيح سرية ولا أموالًا."
    );

    modal.appendChild(
      button(
        "🪙 LOBSTR — اتصال من الهاتف",
        connectLOBSTR,
        true
      )
    );

    modal.appendChild(
      button(
        "✦ StellarTerm — فتح الموقع",
        () => window.open(
          "https://stellarterm.com/",
          "_blank",
          "noopener,noreferrer"
        )
      )
    );

    modal.appendChild(
      make(
        "p",
        "",
        "Telegram Wallet وBinance Web3 " +
        "غير مفعّلين لعملة EN96 على Stellar."
      )
    );

    closeButton(modal);
  }

  async function preparePairing(uri) {
    const modal = dialog(
      "🪙 الاتصال بـ LOBSTR",
      "من هاتف واحد اضغط فتح LOBSTR مباشرة. " +
      "إذا لم يفتح التطبيق، جرّب الرابط البديل. " +
      "يمكن عرض QR على جهاز آخر عند الحاجة."
    );

    const encoded = encodeURIComponent(uri);

    // LOBSTR wallet-specific links.
    // Must be tested on Android / Telegram WebView.
    const deepLink =
      "lobstr://wc?uri=" + encoded;

    const universalLink =
      "https://lobstr.co/uni/wc?uri=" + encoded;

    modal.appendChild(
      button(
        "📱 فتح تطبيق LOBSTR مباشرة",
        () => {
          status(
            "⏳ تم طلب فتح LOBSTR. " +
            "وافق على الاتصال إن ظهر طلب EN96."
          );
          window.location.href = deepLink;
        },
        true
      )
    );

    modal.appendChild(
      button(
        "🌐 تجربة رابط LOBSTR البديل",
        () => {
          window.location.href = universalLink;
        }
      )
    );

    modal.appendChild(
      make(
        "p",
        "",
        "إذا كان التطبيق لا يدعم هذه الروابط " +
        "في نسختك، استخدم QR كخيار احتياطي."
      )
    );

    const qrHolder = make("div");
    modal.appendChild(qrHolder);

    const qrButton = button(
      "▦ عرض رمز QR الاحتياطي",
      async () => {
        qrButton.disabled = true;

        try {
          const qrModule = await import(
            "https://esm.sh/qrcode@1.5.4?bundle"
          );

          const QRCode =
            qrModule.default || qrModule;

          const image = make("img", "en96-wc-qr");
          image.alt = "WalletConnect pairing QR";
          image.src = await QRCode.toDataURL(
            uri,
            { width: 300, margin: 2 }
          );

          qrHolder.replaceChildren(image);
        } catch (error) {
          qrHolder.textContent =
            "تعذر عرض QR على هذا المتصفح.";
        } finally {
          qrButton.disabled = false;
        }
      }
    );

    modal.appendChild(qrButton);

    modal.appendChild(
      make(
        "p",
        "",
        "بعد الموافقة، ارجع إلى صفحة EN96 " +
        "داخل Telegram لمعرفة نتيجة الاتصال."
      )
    );

    closeButton(modal);
  }

  async function connectLOBSTR() {
    if (connecting) return;

    connecting = true;
    status("⏳ إنشاء طلب الاتصال بـ LOBSTR...");

    try {
      const signClient = await getClient();

      const { uri, approval } =
        await signClient.connect({
          requiredNamespaces: {
            stellar: {
              chains: [CONFIG.network],
              methods: ["stellar_signXDR"],
              events: []
            }
          }
        });

      if (!uri) {
        throw new Error(
          "لم يُنشأ رمز اقتران جديد."
        );
      }

      await preparePairing(uri);

      // Wait for wallet approval; connection remains
      // pending while user switches to LOBSTR.
      const approved = await approval();

      const publicAddress =
        getStellarAddress(approved);

      session = approved;
      address = publicAddress;

      closeModal();
      showAddress();

      status(
        "✅ تمت الموافقة على اتصال Stellar.\n" +
        "🔒 لم يتم إثبات ملكية العنوان " +
        "بتوقيع يتحقق منه الخادم بعد.\n" +
        "⚡ Boost غير مفعّل."
      );

    } catch (error) {
      closeModal();

      status(
        "⚠️ لم يكتمل الاتصال: " +
        (error?.message || "خطأ غير معروف.")
      );

      console.error(
        "EN96 WalletConnect:", error
      );
    } finally {
      connecting = false;
    }
  }

  async function loadWallet() {
    const initData =
      window.Telegram?.WebApp?.initData || "";

    if (!initData) {
      throw new Error(
        "افتح EN96 من داخل Telegram."
      );
    }

    const response = await fetch(
      CONFIG.apiBase + "/api/me",
      {
        headers: {
          Authorization: "tma " + initData
        },
        cache: "no-store"
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.error || "تعذر تحميل المحفظة."
      );
    }

    return {
      address: data.stellar_public_address || "",
      available: data.available,
      reserved: data.reserved,
      verified: false
    };
  }

  function initialize() {
    styles();

    const wallet = document.getElementById("wallet");

    if (!wallet) return;

    if (
      document.getElementById("en96ConnectWallet")
    ) return;

    const connectButton = make(
      "button",
      "en96-wc-main",
      "👑 Connect Wallet"
    );

    connectButton.id = "en96ConnectWallet";
    connectButton.addEventListener(
      "click",
      openWalletChooser
    );

    const info = make(
      "div",
      "en96-wc-status",
      "🔒 ربط المحفظة اختياري.\n" +
      "يمكنك التسجيل والتعدين دون اتصال LOBSTR."
    );

    info.id = "en96WCStatus";

    const addressBox = make(
      "div",
      "en96-wc-address"
    );

    addressBox.id = "en96WCAddress";

    const title =
      wallet.querySelector(".page-title");

    if (title) {
      title.insertAdjacentElement(
        "afterend",
        connectButton
      );
    } else {
      wallet.prepend(connectButton);
    }

    connectButton.insertAdjacentElement(
      "afterend",
      info
    );

    info.insertAdjacentElement(
      "afterend",
      addressBox
    );
  }

  window.EN96Wallet = Object.freeze({
    config: CONFIG,
    loadWallet,
    connectLOBSTR,
    openModal: openWalletChooser,
    getState: () => ({
      connected: Boolean(session),
      address,
      verified: false,
      network: CONFIG.network
    }),
    validStellarAddress: value =>
      typeof value === "string" &&
      /^G[A-Z2-7]{55}$/.test(value.trim())
  });

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      initialize,
      { once: true }
    );
  } else {
    initialize();
  }
})();
