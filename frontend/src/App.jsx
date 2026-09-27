/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Application Shell
 *
 * Purpose:
 *   Holds the session, decides which screen is shown, and
 *   provides the navigation, notification tray and theme that
 *   surround every page.
 *
 * Responsibilities:
 *   - Decide between the login screen and the application.
 *   - Load the signed-in officer's identity and jurisdiction.
 *   - Show only the screens that officer's role allows.
 *   - Move between screens and carry the selected record.
 *   - Poll for unresolved alerts and show them in the tray.
 *   - Return to the login screen when the session ends.
 *
 * How it works:
 *
 *   Navigation without a router
 *   ---------------------------
 *   This project does not use React Router. A single piece of
 *   state, activePage, holds the name of the current screen,
 *   and the render body mounts the matching page component.
 *
 *   The consequences are deliberate and must be understood
 *   before adding a screen: there are no URLs for individual
 *   screens, the browser back button does not move between
 *   them, and a refresh returns to the Dashboard. A router
 *   was judged unnecessary for an internal tool used by a
 *   small number of officers on a single deployment.
 *
 *   Because there is no route parameter either, a screen that
 *   needs to know WHICH record to open reads it from state
 *   held here: selectedForestId does the job that /forest/:id
 *   would otherwise do.
 *
 *   Pages never navigate themselves. They are handed
 *   callbacks such as onBack and onViewDetails, and this
 *   module decides what those mean. That keeps every page
 *   independent of every other page: no page imports another.
 *
 *   Sessions
 *   --------
 *   isAuthenticated is seeded from hasStoredToken(), so a
 *   refresh resumes the session rather than forcing a fresh
 *   sign-in. The token itself is never inspected here; only
 *   the server can judge whether it is still valid.
 *
 *   When it stops being valid, the API client detects the
 *   401 and calls every subscriber registered through
 *   onSessionExpired(). This module is one of those
 *   subscribers, and responds by returning to the login
 *   screen. Handling it in one place means no page has to
 *   check for an ended session before trusting a response.
 *
 *   Role-based screens
 *   ------------------
 *   isAdministrator() and supervisesMultipleDistricts()
 *   decide which navigation entries and panels appear.
 *
 *   This is presentation, NOT access control. The server
 *   enforces jurisdiction independently in its repository
 *   layer, and refuses an out-of-jurisdiction record however
 *   it is requested. An interface that merely hides data is
 *   not security; a query that cannot return it is.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 * ===========================================================
 */

import {
  useEffect,
  useRef,
  useState,
} from "react";

import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  ChevronDown,
  Clock,
  LayoutDashboard,
  Leaf,
  LogOut,
  Info,
  Menu,
  Moon,
  Satellite,
  Search,
  Settings,
  ShieldCheck,
  Sun,
  TreePine,
  X,
} from "lucide-react";

import Analysis from "./pages/Analysis";
import Alerts from "./pages/Alerts";
import Dashboard from "./pages/Dashboard";
import Detections from "./pages/Detections";
import ForestAreaDetails from "./pages/ForestAreaDetails";
import ForestAreas from "./pages/ForestAreas";
import Login from "./pages/Login";
import RegisterForestArea from "./pages/RegisterForestArea";
import SatelliteImages from "./pages/SatelliteImages";
import SettingsPage from "./pages/Settings";
import About from "./pages/About";
import UserManagement from "./pages/UserManagement";

import DistrictBreakdown from "./components/DistrictBreakdown";
import useCurrentUser from "./hooks/useCurrentUser";
import { onSessionExpired } from "./services/api";

import { API_URL as CONFIG_API_URL } from "./config";
import {
  describeJurisdiction,
  describeRole,
  hasStoredToken,
  initialsFor,
  isAdministrator,
  isAwaitingJurisdiction,
  supervisesMultipleDistricts,
  logout as clearSession,
} from "./services/auth";

const API_URL = CONFIG_API_URL;

function App() {
  // A token already in storage means the officer signed in
  // during an earlier visit, so the interface restores the
  // session instead of asking them to sign in again on
  // every page refresh.
  const [isAuthenticated, setIsAuthenticated] =
    useState(hasStoredToken);

  // Identity and jurisdiction of the signed-in officer.
  const {
    currentUser,
    error: currentUserError,
  } = useCurrentUser(isAuthenticated);

  const [darkMode, setDarkMode] =
    useState(false);

  const [sidebarOpen, setSidebarOpen] =
    useState(true);

  const [activePage, setActivePage] =
    useState("Dashboard");

  const [selectedForestId, setSelectedForestId] =
    useState(null);

  const [notifications, setNotifications] =
    useState([]);

  const [notificationOpen, setNotificationOpen] =
    useState(false);

  const [notificationLoading, setNotificationLoading] =
    useState(false);

  const [readNotificationIds, setReadNotificationIds] =
    useState(() => {
      try {
        const saved = localStorage.getItem(
          "forestwatch_read_notifications"
        );

        return saved ? JSON.parse(saved) : [];
      } catch {
        return [];
      }
    });

  const notificationRef = useRef(null);

  // -------------------------------------------------------
  // Navigation
  //
  // Operational pages are available to every signed-in
  // officer. Account administration is shown only to
  // administrators.
  //
  // Hiding a page is presentation, NOT access control. The
  // server refuses an out-of-jurisdiction record and a
  // non-administrator's request to manage accounts whether
  // or not the interface offers the link.
  // -------------------------------------------------------

  const navigation = [
    {
      name: "Dashboard",
      icon: LayoutDashboard,
    },
    {
      name: "Forest Areas",
      icon: TreePine,
    },
    {
      name: "Analysis",
      icon: Satellite,
    },
    {
      name: "Detections",
      icon: Leaf,
    },
    {
      name: "Alerts",
      icon: Bell,
    },
    {
      name: "Satellite Images",
      icon: Satellite,
    },
  ];

  if (isAdministrator(currentUser)) {
    navigation.push({
      name: "User Management",
      icon: ShieldCheck,
    });
  }

  // -------------------------------------------------------
  // End the session when the server rejects the token
  //
  // Tokens expire while the interface is open. Without
  // this, every page would simply stop returning data and
  // an expired session would look like an empty database.
  // -------------------------------------------------------

  useEffect(() => {
    return onSessionExpired(() => {
      setIsAuthenticated(false);
      setActivePage("Dashboard");
    });
  }, []);

  /**
   * Sign the current officer out.
   *
   * The stored token is discarded and the interface returns
   * to the sign-in screen. Returning to Dashboard prevents
   * the next officer from landing on a page the previous
   * one had open.
   */
  const handleSignOut = () => {
    clearSession();

    setIsAuthenticated(false);
    setActivePage("Dashboard");
    setSelectedForestId(null);
  };

  useEffect(() => {
    localStorage.setItem(
      "forestwatch_read_notifications",
      JSON.stringify(readNotificationIds)
    );
  }, [readNotificationIds]);

  const fetchNotifications = async () => {
    try {
      setNotificationLoading(true);

      const token =
        localStorage.getItem("access_token") ||
        localStorage.getItem("token");

      if (!token) {
        return;
      }

      const response = await fetch(
        `${API_URL}/api/v1/alerts`,
        {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(
          `Unable to load notifications. Server returned ${response.status}.`
        );
      }

      const data = await response.json();

      const alerts = Array.isArray(data)
        ? data
        : [];

      setNotifications(alerts);

      const backendReadIds = alerts
        .filter(
          (alert) => alert.is_read === true
        )
        .map((alert) => alert.id);

      if (backendReadIds.length > 0) {
        setReadNotificationIds((current) => [
          ...new Set([
            ...current,
            ...backendReadIds,
          ]),
        ]);
      }
    } catch (error) {
      console.error(
        "Notification Error:",
        error
      );
    } finally {
      setNotificationLoading(false);
    }
  };

  const markNotificationAsRead = async (
    alertId
  ) => {
    try {
      const token =
        localStorage.getItem("access_token") ||
        localStorage.getItem("token");

      if (!token) {
        return;
      }

      setReadNotificationIds((current) => [
        ...new Set([
          ...current,
          alertId,
        ]),
      ]);

      const response = await fetch(
        `${API_URL}/api/v1/alerts/${alertId}/read`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        console.error(
          `Failed to mark alert ${alertId} as read.`
        );
      }
    } catch (error) {
      console.error(
        "Mark notification as read error:",
        error
      );
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchNotifications();
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    const interval = setInterval(() => {
      fetchNotifications();
    }, 60000);

    return () => {
      clearInterval(interval);
    };
  }, [isAuthenticated]);

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (
        notificationRef.current &&
        !notificationRef.current.contains(
          event.target
        )
      ) {
        setNotificationOpen(false);
      }
    };

    document.addEventListener(
      "mousedown",
      handleOutsideClick
    );

    return () => {
      document.removeEventListener(
        "mousedown",
        handleOutsideClick
      );
    };
  }, []);

  const unreadNotifications =
    notifications.filter((notification) => {
      const isRead =
        notification.is_read === true ||
        readNotificationIds.includes(
          notification.id
        );

      const isResolved =
        notification.is_resolved === true ||
        notification.status === "RESOLVED";

      return !isRead && !isResolved;
    });

  const formatNotificationDate = (date) => {
    if (!date) {
      return "";
    }

    try {
      return new Date(date).toLocaleString(
        "en-ZM",
        {
          day: "2-digit",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        }
      );
    } catch {
      return "";
    }
  };

  const getPriorityClass = (priority) => {
    const value = String(
      priority || ""
    ).toLowerCase();

    if (value === "critical") {
      return "notification-priority critical";
    }

    if (value === "high") {
      return "notification-priority high";
    }

    if (value === "medium") {
      return "notification-priority medium";
    }

    return "notification-priority low";
  };

  if (!isAuthenticated) {
    return (
      <Login
        onLogin={() => {
          setIsAuthenticated(true);
          setActivePage("Dashboard");
          setSelectedForestId(null);
        }}
      />
    );
  }

  return (
    <div className={darkMode ? "app dark" : "app"}>

      <aside
        className={`sidebar ${
          sidebarOpen ? "open" : "closed"
        }`}
      >
        <div className="brand">
          <div className="brand-mark">
            <TreePine
              size={24}
              strokeWidth={2.2}
            />
          </div>

          {sidebarOpen && (
            <div className="brand-text">
              <strong>
                ForestWatch
              </strong>

              <span>
                ZAMBIA
              </span>
            </div>
          )}

          {sidebarOpen && (
            <button
              className="mobile-close"
              onClick={() =>
                setSidebarOpen(false)
              }
              aria-label="Close sidebar"
            >
              <X size={20} />
            </button>
          )}
        </div>

        <div className="sidebar-section">
          {sidebarOpen && (
            <p className="section-label">
              MONITORING
            </p>
          )}

          <nav>
            {navigation.map((item) => {
              const Icon = item.icon;

              return (
                <button
                  key={item.name}
                  className={`nav-item ${
                    activePage === item.name
                      ? "active"
                      : ""
                  }`}
                  onClick={() => {
                    setActivePage(
                      item.name
                    );

                    if (
                      item.name !==
                      "Forest Areas"
                    ) {
                      setSelectedForestId(
                        null
                      );
                    }
                  }}
                >
                  <Icon size={20} />

                  {sidebarOpen && (
                    <span>
                      {item.name}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="sidebar-bottom">
          <button
            className={`nav-item ${
              activePage === "Settings"
                ? "active"
                : ""
            }`}
            onClick={() => {
              setActivePage("Settings");
              setSelectedForestId(null);
            }}
          >
            <Settings size={20} />

            {sidebarOpen && (
              <span>
                Settings
              </span>
            )}
          </button>

          {/* Sits below Settings rather than in the main
              navigation: it describes the system rather than
              being part of the monitoring work, and it is
              also where an officer is sent when they need to
              check whether the server is reachable. */}
          <button
            className={`nav-item ${
              activePage === "About"
                ? "active"
                : ""
            }`}
            onClick={() => {
              setActivePage("About");
              setSelectedForestId(null);
            }}
          >
            <Info size={20} />

            {sidebarOpen && (
              <span>
                About
              </span>
            )}
          </button>

          {sidebarOpen && (
            <div className="institution-card">
              <ShieldCheck size={20} />

              <div>
                <strong>
                  Zambia University
                </strong>

                <span>
                  College of Technology
                </span>
              </div>
            </div>
          )}
        </div>
      </aside>

      <div className="main-area">

        <header className="topbar">
          <div className="topbar-left">

            <button
              className="icon-button"
              onClick={() =>
                setSidebarOpen(
                  !sidebarOpen
                )
              }
              aria-label="Toggle sidebar"
            >
              <Menu size={21} />
            </button>

            <div className="breadcrumb">
              <span>
                ForestWatch Zambia
              </span>

              <strong>
                /
              </strong>

              <span className="current">
                {activePage}
              </span>
            </div>
          </div>

          <div className="topbar-right">

            <div className="search-box">
              <Search size={18} />

              <input
                type="search"
                placeholder="Search..."
                aria-label="Search"
              />
            </div>

            <button
              className="icon-button"
              onClick={() =>
                setDarkMode(!darkMode)
              }
              aria-label="Toggle theme"
            >
              {darkMode ? (
                <Sun size={20} />
              ) : (
                <Moon size={20} />
              )}
            </button>

            <div
              className="notification-wrapper"
              ref={notificationRef}
            >
              <button
                className={`notification-button ${
                  notificationOpen
                    ? "notification-active"
                    : ""
                }`}
                onClick={() => {
                  const opening =
                    !notificationOpen;

                  setNotificationOpen(
                    opening
                  );

                  if (opening) {
                    fetchNotifications();
                  }
                }}
                title="Notifications"
                aria-label="Notifications"
              >
                <Bell size={20} />

                {unreadNotifications.length >
                  0 && (
                  <span className="notification-count">
                    {unreadNotifications.length >
                    9
                      ? "9+"
                      : unreadNotifications.length}
                  </span>
                )}
              </button>

              {notificationOpen && (
                <div className="notification-panel">

                  <div className="notification-panel-header">
                    <div>
                      <h3>
                        Notifications
                      </h3>

                      <span>
                        Forest monitoring alerts
                      </span>
                    </div>

                    <button
                      className="notification-refresh"
                      onClick={
                        fetchNotifications
                      }
                      aria-label="Refresh notifications"
                    >
                      ↻
                    </button>
                  </div>

                  <div className="notification-list">

                    {notificationLoading && (
                      <div className="notification-empty">
                        <div className="notification-spinner">
                          ⟳
                        </div>

                        <p>
                          Loading alerts...
                        </p>
                      </div>
                    )}

                    {!notificationLoading &&
                      notifications.length ===
                        0 && (
                        <div className="notification-empty">
                          <Bell size={28} />

                          <strong>
                            No notifications
                          </strong>

                          <p>
                            There are currently no
                            forest monitoring alerts.
                          </p>
                        </div>
                    )}

                    {!notificationLoading &&
                      notifications
                        .slice(0, 5)
                        .map(
                          (
                            notification
                          ) => {
                            const isRead =
                              notification.is_read ===
                                true ||
                              readNotificationIds.includes(
                                notification.id
                              );

                            return (
                              <div
                                className={`notification-item ${
                                  notification.is_resolved
                                    ? "resolved"
                                    : ""
                                } ${
                                  isRead
                                    ? "notification-read"
                                    : "notification-unread"
                                }`}
                                key={
                                  notification.id
                                }
                                onClick={() => {
                                  if (!isRead) {
                                    markNotificationAsRead(
                                      notification.id
                                    );
                                  }
                                }}
                              >
                                <div className="notification-item-icon">
                                  {notification.priority ===
                                  "CRITICAL" ? (
                                    <AlertTriangle
                                      size={18}
                                    />
                                  ) : notification.is_resolved ? (
                                    <CheckCircle2
                                      size={18}
                                    />
                                  ) : (
                                    <Bell
                                      size={18}
                                    />
                                  )}
                                </div>

                                <div className="notification-item-content">
                                  <div className="notification-title-row">
                                    <strong>
                                      {
                                        notification.title
                                      }
                                    </strong>

                                    <span
                                      className={getPriorityClass(
                                        notification.priority
                                      )}
                                    >
                                      {
                                        notification.priority
                                      }
                                    </span>
                                  </div>

                                  <p>
                                    {
                                      notification.message
                                    }
                                  </p>

                                  <div className="notification-meta">
                                    <span>
                                      <Clock
                                        size={13}
                                      />

                                      {formatNotificationDate(
                                        notification.created_at
                                      )}
                                    </span>

                                    {notification.is_resolved && (
                                      <span className="notification-resolved">
                                        Resolved
                                      </span>
                                    )}

                                    {isRead && (
                                      <span className="notification-read-label">
                                        Read
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );
                          }
                        )}
                  </div>

                  <div className="notification-panel-footer">
                    <span>
                      {
                        unreadNotifications.length
                      }{" "}
                      unread
                    </span>

                    <button
                      onClick={() =>
                        setNotificationOpen(
                          false
                        )
                      }
                    >
                      Close
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div
              className="user-profile"
              title={
                currentUser
                  ? `${describeRole(currentUser)} - ` +
                    `${describeJurisdiction(currentUser)}`
                  : "Loading your profile"
              }
            >
              <div className="avatar">
                {initialsFor(currentUser)}
              </div>

              <div className="user-details">
                <strong>
                  {currentUser?.full_name || "Signing in..."}
                </strong>

                {/*
                  The jurisdiction is shown rather than a
                  generic label, so an officer can always
                  see which area the records in front of
                  them are limited to.
                */}
                <span>
                  {currentUser
                    ? describeJurisdiction(currentUser)
                    : ""}
                </span>
              </div>

              <ChevronDown size={17} />
            </div>

            {/*
              Signing out matters on a shared departmental
              workstation: without it, the next person to
              use the machine inherits the previous
              officer's session and their jurisdiction.
            */}
            <button
              type="button"
              className="sign-out-button"
              onClick={handleSignOut}
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut size={18} />
            </button>
          </div>
        </header>

        <main className="content">

          {/*
            An officer with no district or province assigned
            is refused every record by the server, so every
            page would show an empty list. Saying so plainly
            prevents that being read as "no deforestation
            has been detected".
          */}
          {isAwaitingJurisdiction(currentUser) && (
            <div className="jurisdiction-notice">
              <AlertTriangle size={18} />

              <div>
                <strong>
                  No jurisdiction has been assigned to your
                  account.
                </strong>

                <span>
                  Forest areas, detections and alerts are
                  restricted to the district or province an
                  officer is responsible for. Until an
                  administrator assigns yours, these pages
                  will appear empty. This is not an
                  indication that no deforestation has been
                  detected.
                </span>
              </div>
            </div>
          )}

          {currentUserError && (
            <div className="jurisdiction-notice">
              <AlertTriangle size={18} />

              <div>
                <span>{currentUserError}</span>
              </div>
            </div>
          )}

          {activePage === "Dashboard" && (
            <>
              {/*
                Only officers responsible for more than one
                district see a comparison between them. A
                district officer supervises one, so the
                server refuses the request and the component
                renders nothing.
              */}
              <DistrictBreakdown
                visible={supervisesMultipleDistricts(
                  currentUser
                )}
              />

              <Dashboard />
            </>
          )}

          {activePage === "Analysis" && (
            <Analysis />
          )}

          {activePage === "Forest Areas" && (
            <ForestAreas
              onRegister={() => {
                setSelectedForestId(null);
                setActivePage(
                  "Register Forest Area"
                );
              }}
              onViewDetails={(forestId) => {
                setSelectedForestId(
                  forestId
                );

                setActivePage(
                  "Forest Area Details"
                );
              }}
            />
          )}

          {activePage ===
            "Register Forest Area" && (
            <RegisterForestArea
              onBack={() => {
                setActivePage(
                  "Forest Areas"
                );
              }}
              onRegistered={() => {
                setSelectedForestId(null);
                setActivePage(
                  "Forest Areas"
                );
              }}
            />
          )}

          {activePage ===
            "Forest Area Details" && (
            <ForestAreaDetails
              forestId={
                selectedForestId
              }
              onBack={() => {
                setSelectedForestId(null);
                setActivePage(
                  "Forest Areas"
                );
              }}
            />
          )}

          {activePage === "Detections" && (
            <Detections />
          )}

          {activePage === "Alerts" && (
            <Alerts />
          )}

          {activePage ===
            "Satellite Images" && (
            <SatelliteImages />
          )}

          {activePage === "Settings" && (
            <SettingsPage />
          )}

          {activePage === "About" && (
            <About />
          )}

          {/*
            Rendered only for administrators. The page is
            also removed from the navigation for everyone
            else, and the endpoints it calls are restricted
            to administrators on the server, so this check
            is the least important of the three.
          */}
          {activePage === "User Management" &&
            isAdministrator(currentUser) && (
              <UserManagement />
            )}
        </main>

        <footer className="footer">
          <span>
            ForestWatch Zambia
          </span>

          <span>
            •
          </span>

          <span>
            Zambia University College
            of Technology
          </span>

          <span>
            •
          </span>

          <span>
            Intelligent Forest Monitoring
          </span>
        </footer>
      </div>
    </div>
  );
}

export default App;