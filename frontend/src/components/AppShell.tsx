import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { NavLink, Outlet, useLocation, useNavigate, type To } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { UploaderProvider, useSharedUploader } from "../features/library/UploadControl";
import { displayName, initialOf } from "../auth/displayName";
import { formatDate } from "../lib/format";
import { t } from "../i18n";
import { Wordmark } from "./Wordmark";

/**
 * Every signed-in page: a slim top bar (menu and wordmark) and the page. The
 * menu opens a sidebar from the left over the page; uploading starts from
 * the library page or from the sidebar.
 */
export function AppShell() {
  return (
    <UploaderProvider>
      <Shell />
    </UploaderProvider>
  );
}

const CLOSE_MS = 180;

function Shell() {
  const drawerRef = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const { pathname } = useLocation();
  const uploader = useSharedUploader();
  const navigate = useNavigate();

  const openDrawer = () => {
    const dialog = drawerRef.current;
    dialog?.showModal();
    // Focus the panel, not its first button: the close button is then not
    // focused (and ringed) until it is reached with Tab.
    dialog?.querySelector<HTMLElement>(".sidebar__inner")?.focus();
    setClosing(false);
    setOpen(true);
  };

  // Slide out first, then close the dialog (which returns focus to the menu button).
  const closeDrawer = useCallback(() => {
    const dialog = drawerRef.current;
    if (!dialog?.open) return;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setClosing(true);
    window.setTimeout(
      () => {
        dialog.close();
        setClosing(false);
        setOpen(false);
      },
      still ? 0 : CLOSE_MS,
    );
  }, []);

  // A new page closes the sidebar (also after Back/Forward while it is open).
  useEffect(closeDrawer, [pathname, closeDrawer]);

  function upload() {
    // Open the picker within this click (browsers require a user gesture);
    // the chosen file then waits on the library page.
    uploader.pick();
    if (pathname !== "/") navigate("/");
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        {t("nav.skipToContent")}
      </a>

      <header className="topbar">
        <div className="topbar__inner">
          <button
            type="button"
            className="topbar__menu"
            onClick={openDrawer}
            aria-label={t("nav.openMenu")}
            aria-haspopup="dialog"
            aria-expanded={open}
            aria-controls="app-sidebar"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M3 5.5h14M3 10h14M3 14.5h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
          <Wordmark to="/" />
        </div>
      </header>

      <dialog
        ref={drawerRef}
        id="app-sidebar"
        className={`sidebar${closing ? " sidebar--closing" : ""}`}
        aria-label={t("nav.main")}
        // Esc: slide out like every other close.
        onCancel={(event) => {
          event.preventDefault();
          closeDrawer();
        }}
        // A click on the backdrop lands on the dialog element itself.
        onClick={(event) => event.target === event.currentTarget && closeDrawer()}
      >
        <Sidebar onClose={closeDrawer} onUpload={upload} />
      </dialog>

      <main id="main" className="shell__main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}

function Sidebar({ onClose, onUpload }: { onClose: () => void; onUpload: () => void }) {
  const { session, signOut } = useAuth();
  const uploader = useSharedUploader();
  const { pathname } = useLocation();
  const user = session?.user;
  const email = user?.email ?? "";
  const name = displayName(user);
  const initial = initialOf(name);
  const since = formatDate(user?.created_at);
  // A book belongs to the library, so the library stays marked on book pages.
  const inLibrary = pathname === "/" || pathname.startsWith("/books/");

  /**
   * A sidebar link: on its own page it only closes the sidebar (no reload,
   * no duplicate history entry); elsewhere it navigates, and the new page
   * closes the sidebar.
   */
  const go = (to: To) => (event: MouseEvent) => {
    if (to === pathname) {
      event.preventDefault();
      onClose();
    }
  };

  return (
    <div className="sidebar__inner" tabIndex={-1}>
      <div className="sidebar__top">
        {/* Plain text here: My Library, just below, is the way back to the library. */}
        <Wordmark />
        <button type="button" className="sidebar__close" onClick={onClose} aria-label={t("nav.closeMenu")}>
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <section className="sidebar__account" aria-label={t("nav.account")}>
        <span className="avatar" aria-hidden="true">
          {initial}
        </span>
        <div className="sidebar__who">
          <p className="sidebar__name" title={email}>
            {name}
          </p>
          {since && <p className="sidebar__since">{t("nav.memberSince", { date: since })}</p>}
        </div>
      </section>

      <nav className="sidebar__nav" aria-label={t("nav.sections")}>
        <NavLink to="/" end className="sidebar__link" aria-current={inLibrary ? "page" : undefined} onClick={go("/")}>
          {t("nav.library")}
        </NavLink>
        <button
          type="button"
          className="sidebar__link"
          onClick={() => {
            onUpload();
            onClose();
          }}
          disabled={uploader.busy}
        >
          {uploader.busy ? t("nav.uploading") : t("nav.uploadBook")}
        </button>
      </nav>

      <div className="sidebar__foot">
        <NavLink to="/help" className="sidebar__link" onClick={go("/help")}>
          {t("nav.help")}
        </NavLink>
        <button
          type="button"
          className="sidebar__link sidebar__link--quiet"
          onClick={() => {
            onClose();
            void signOut();
          }}
        >
          {t("nav.signOut")}
        </button>
      </div>
    </div>
  );
}
