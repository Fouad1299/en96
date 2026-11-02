
/*
 EN96 ICE BEAR KINGDOM
 Stellar WalletConnect

 Stage 1: Wallet connection only.
 No payments, no balance changes,
 no ownership verification yet.
*/

(function () {
  "use strict";

  const PROJECT_ID =
    "3e9fa0461e993b4dbc10fb444a3ca46f";

  const NETWORK = "stellar:pubnet";

  const BASE_URL =
    "https://fouad1299.github.io/en96/";

  let signClient = null;
  let activeSession = null;
  let activeAddress = null;
  let busy = false;

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function setStatus(message) {
    const status = document.getElementById(
      "en96WalletConnectionStatus"
    );

    if (status) status.textContent = message;
  }

  function styles() {
    if (document.getElementById("en96WCStyles")) {
      return;
    }

    const sheet = element("style");
    sheet.id = "en96WCStyles";

    sheet.textContent = `
      .en96-wc-button {
        width:100%;
        padding:17px;
        margin:15px 0;
        border:1px solid #fff2ad;
        border-radius:17px;
        color:#4b2100;
        background:linear-gradient(
          135deg,#fff1a0,#ffcc3f,#ff9c13
        );
        font-weight:900;
        font-size:18px;
        cursor:pointer;
      }

      .en96-wc-status {
        background:#27100d;
        color:#ffe3ac;
        padding:13px;
        border:1px solid #a77a43;
        border-radius:12px;
        font-size:12px;
        line-height:1.8;
        margin-bottom:15px;
        overflow-wrap:anywhere;
      }

      .en96-wc-overlay {
        position:fixed;
        inset:0;
        z-index:99999;
        display:flex;
        justify-content:center;
        align-items:center;
        padding:16px;
        background:rgba(0,0,0,.85);
      }

      .en96-wc-modal {
        width:100%;
        max-width:460px;
        max-height:87dvh;
        overflow:auto;
        border:2px solid #edbc55;
        border-radius:23px;
        background:linear-gradient(
          145deg,#502015,#210c0b
        );
        padding:18px;
        color:white;
        text-align:center;
        direction:rtl;
      }

      .en96-wc-modal h2 {
        color:#ffdf8d;
        margin:4px 0 13px;
      }

      .en96-wc-modal p {
        font-size:12px;
        line-height:1.8;
        color:#ffe2cc;
      }

      .en96-wc-choice {
        display:block;
        width:100%;
        padding:17px;
        margin-top:12px;
        background:#37140e;
        color:#ffedcd;
        border:1px solid #c89551;
        border-radius:15px;
        font-size:15px;
        font-weight:800;
        cursor:pointer;
      }

      .en96-wc-choice:disabled {
        opacity:.5;
      }

      .en96-wc-qr {
        display:block;
        width:min(72vw,280px);
        max-width:100%;
        margin:14px auto;
        padding:12px;
        background:white;
        border-radius:14px;
      }

      .en96-wc-close {
        width:100%;
        margin-top:15px;
        padding:13px;
        color:#ffe3a0;
        background:#632717;
        border:1px solid #b27b42;
        border-radius:13px;
        cursor:pointer;
      }

      .en96-wc-address {
        direction:ltr;
        text-align:left;
        overflow-wrap:anywhere;
        color:#ffe59e;
        padding:12px;
        font-size:12px;
        border:1px solid #9b713b;
        border-radius:10px;
        margin-top:12px;
      }
    `;

    document.head.appendChild(sheet);
  }

  function closeModal() {
    document.getElementById(
      "en96WCOverlay"
    )?.remove();
  }

  function openModal() {
    closeModal();

    const overlay = element(
      "div",
      "en96-wc-overlay"
    );
    overlay.id = "en96WCOverlay";

    const modal = element(
      "div",
      "en96-wc-modal"
    );

    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");

    const heading = element(
      "h2", "", "👑 Connect Wallet"
    );

    modal.appendChild(heading);

    const intro = element(
      "p",
      "",
      "اختر محفظتك على شبكة Stellar. " +
      "لن نطلب مفتاحك السري أو إرسال أموال."
    );
    modal.appendChild(intro);

    const lobstr = element(
      "button",
      "en96-wc-choice",
      "🪙 LOBSTR — WalletConnect"
    );
    lobstr.onclick = connectLOBSTR;
    modal.appendChild(lobstr);

    const term = element(
      "button",
      "en96-wc-choice",
      "✦ StellarTerm — فتح الموقع"
    );
    term.onclick = () => {
      window.open(
        "https://stellarterm.com/",
        "_blank",
        "noopener,noreferrer"
      );
    };
    modal.appendChild(term);

    const unavailable = element(
      "p",
      "",
      "Binance Web3 وTelegram Wallet: " +
      "لم يتم تفعيل استقبال EN96 " +
      "عبرهما على Stellar."
    );
    modal.appendChild(unavailable);

    const close = element(
      "button",
      "en96-wc-close",
      "✕ إغلاق"
    );
    close.onclick = closeModal;
    modal.appendChild(close);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    overlay.addEventListener("click", e => {
      if (e.target === overlay) closeModal();
    });

    return modal;
  }

  async function getClient() {
    if (signClient) return signClient;

    const sdk = await import(
      "https://esm.sh/" +
      "@walletconnect/sign-client@2.26.0" +
      "?bundle"
    );

    const SignClient =
      sdk.default || sdk.SignClient;

    signClient = await SignClient.init({
      projectId: PROJECT_ID,
      metadata: {
        name: "EN96 Ice Bear Kingdom",
        description:
          "EN96 Stellar wallet connection",
        url: BASE_URL,
        icons: [
          BASE_URL + "en96-coin.webp"
        ]
      }
    });

    signClient.on("session_delete", () => {
      activeSession = null;
      activeAddress = null;
      setStatus("🔒 تم قطع اتصال المحفظة.");
    });

    return signClient;
  }

  async function showPairing(uri, modal) {
    modal.innerHTML = "";

    modal.appendChild(
      element(
        "h2", "", "🪙 اتصال LOBSTR"
      )
    );

    modal.appendChild(
      element(
        "p",
        "",
        "امسح رمز QR من LOBSTR " +
        "ثم وافق على طلب اتصال EN96 فقط."
      )
    );

    const qrPackage = await import(
      "https://esm.sh/qrcode@1.5.4?bundle"
    );

    const QRCode =
      qrPackage.default || qrPackage;

    const image = element(
      "img", "en96-wc-qr"
    );
    image.alt = "WalletConnect QR";

    image.src = await QRCode.toDataURL(
      uri,
      {
        width: 300,
        margin: 2
      }
    );

    modal.appendChild(image);

    const copy = element(
      "button",
      "en96-wc-choice",
      "📋 نسخ رابط الاتصال للهاتف"
    );

    copy.onclick = async () => {
      try {
        await navigator.clipboard.writeText(uri);
        copy.textContent =
          "✅ تم نسخ رابط الاتصال";
      } catch (error) {
        copy.textContent =
          "تعذر النسخ من المتصفح";
      }
    };

    modal.appendChild(copy);

    modal.appendChild(
      element(
        "p",
        "",
        "إذا كنت تستعمل هاتفًا واحدًا، " +
        "يمكن استعمال رابط الاتصال " +
        "إذا كانت نسختك من LOBSTR " +
        "تتيح فتحه. وإلا يلزم عرض " +
        "رمز QR على جهاز ثانٍ."
      )
    );

    modal.appendChild(
      element(
        "p",
        "",
        "⏳ بانتظار موافقة المحفظة..."
      )
    );

    const close = element(
      "button",
      "en96-wc-close",
      "إغلاق النافذة"
    );
    close.onclick = closeModal;
    modal.appendChild(close);
  }

  async function connectLOBSTR() {
    if (busy) return;

    busy = true;
    setStatus(
      "⏳ تحضير اتصال WalletConnect..."
    );

    const modal = document.querySelector(
      "#en96WCOverlay .en96-wc-modal"
    );

    try {
      const client = await getClient();

      const { uri, approval } =
        await client.connect({
          requiredNamespaces: {
            stellar: {
              chains: [NETWORK],
              methods: [
                "stellar_signXDR"
              ],
              events: []
            }
          }
        });

      if (!uri) {
        throw new Error(
          "لم يتم إنشاء رابط اتصال جديد."
        );
      }

      await showPairing(uri, modal);

      const session = await approval();

      const accounts =
        session?.namespaces?.stellar?.accounts
        || [];

      const prefix = NETWORK + ":";

      const account = accounts.find(a =>
        typeof a === "string" &&
        a.startsWith(prefix)
      );

      const address = account
        ? account.slice(prefix.length)
        : "";

      if (!/^G[A-Z2-7]{55}$/.test(address)) {
        throw new Error(
          "لم تُرجع المحفظة عنوان Stellar صالحًا."
        );
      }

      activeSession = session;
      activeAddress = address;

      closeModal();

      setStatus(
        "✅ وافقت المحفظة على الاتصال.\n" +
        "🔒 إثبات الملكية بالتوقيع " +
        "لم يكتمل بعد، " +
        "ولا توجد زيادة في التعدين."
      );

      const addr = document.getElementById(
        "en96WCAddress"
      );

      if (addr) {
        addr.textContent = address;
      }

    } catch (error) {
      console.error(
        "EN96 WalletConnect error:",
        error
      );

      closeModal();

      setStatus(
        "⚠️ لم يكتمل اتصال LOBSTR: " +
        (error.message || "خطأ غير معروف")
      );
    } finally {
      busy = false;
    }
  }

  function initialize() {
    styles();

    const wallet =
      document.getElementById("wallet");

    if (!wallet) return;

    if (document.getElementById(
      "en96ConnectWallet"
    )) return;

    const button = element(
      "button",
      "en96-wc-button",
      "👑 Connect Wallet"
    );

    button.id = "en96ConnectWallet";
    button.onclick = openModal;

    const status = element(
      "div",
      "en96-wc-status",
      "🔒 لا توجد محفظة متصلة أو " +
      "موثقة بالتوقيع حاليًا."
    );

    status.id = "en96WalletConnectionStatus";

    const address = element(
      "div",
      "en96-wc-address"
    );

    address.id = "en96WCAddress";

    const title = wallet.querySelector(
      ".page-title"
    );

    if (title) {
      title.insertAdjacentElement(
        "afterend", button
      );
    } else {
      wallet.prepend(button);
    }

    button.insertAdjacentElement(
      "afterend", status
    );

    status.insertAdjacentElement(
      "afterend", address
    );
  }

  window.EN96Wallet = Object.freeze({
    connectLOBSTR,
    openModal,
    getState: () => ({
      connected: Boolean(activeSession),
      address: activeAddress,
      verified: false,
      network: NETWORK
    })
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
