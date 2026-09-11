import { useState } from "react";
import {
  AlertCircle,
  Eye,
  EyeOff,
  Leaf,
  Lock,
  Mail,
  TreePine,
} from "lucide-react";
import axios from "axios";

function Login({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (event) => {
    event.preventDefault();

    setError("");

    if (!email.trim() || !password) {
      setError("Please enter your email and password.");
      return;
    }

    try {
      setLoading(true);

      // FastAPI OAuth2PasswordRequestForm
      // requires application/x-www-form-urlencoded.
      const formData = new URLSearchParams();

      formData.append("username", email.trim());
      formData.append("password", password);

      const response = await axios.post(
        "http://127.0.0.1:8000/api/v1/auth/login",
        formData,
        {
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
        }
      );

      const token = response.data?.access_token;

      if (!token) {
        throw new Error("No access token returned by the server.");
      }

      // Save authentication token.
      localStorage.setItem("access_token", token);

      // Tell App.jsx that authentication succeeded.
      onLogin(token);

    } catch (err) {
      console.error("Login error:", err);

      if (err.response) {
        if (err.response.status === 401) {
          setError(
            err.response.data?.detail ||
              "Invalid email or password."
          );
        } else if (err.response.status === 422) {
          setError(
            "The login information could not be processed. Please check your email and password."
          );
        } else {
          setError(
            err.response.data?.detail ||
              "The server returned an error. Please try again."
          );
        }
      } else {
        setError(
          "Unable to connect to ForestWatch Zambia. Please make sure the backend is running."
        );
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">

      <div className="login-container">

        {/* Left branding panel */}
        <div className="login-brand-panel">

          <div className="login-brand-logo">
            <TreePine size={36} />
          </div>

          <h1>ForestWatch</h1>

          <span>ZAMBIA</span>

          <p>
            Intelligent Deforestation Detection
            and Alert System Using Sentinel-2
            Imagery in the Copperbelt, Zambia.
          </p>

          <div className="login-feature">
            <Leaf size={18} />

            <span>
              Intelligent forest monitoring
            </span>
          </div>

          <div className="login-feature">
            <TreePine size={18} />

            <span>
              Sentinel-2 satellite imagery
            </span>
          </div>

        </div>

        {/* Login form */}
        <div className="login-form-panel">

          <div className="login-heading">

            <h2>Welcome back</h2>

            <p>
              Sign in to access ForestWatch Zambia.
            </p>

          </div>

          {error && (
            <div className="login-error">

              <AlertCircle size={18} />

              <span>{error}</span>

            </div>
          )}

          <form onSubmit={handleLogin}>

            {/* Email */}
            <div className="form-group">

              <label htmlFor="email">
                Email address
              </label>

              <div className="input-wrapper">

                <Mail size={18} />

                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(event) =>
                    setEmail(event.target.value)
                  }
                  placeholder="Enter your email"
                  autoComplete="email"
                  disabled={loading}
                />

              </div>

            </div>

            {/* Password */}
            <div className="form-group">

              <label htmlFor="password">
                Password
              </label>

              <div className="input-wrapper">

                <Lock size={18} />

                <input
                  id="password"
                  type={
                    showPassword
                      ? "text"
                      : "password"
                  }
                  value={password}
                  onChange={(event) =>
                    setPassword(event.target.value)
                  }
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  disabled={loading}
                />

                <button
                  type="button"
                  className="password-toggle"
                  onClick={() =>
                    setShowPassword(!showPassword)
                  }
                  aria-label={
                    showPassword
                      ? "Hide password"
                      : "Show password"
                  }
                >

                  {showPassword ? (
                    <EyeOff size={18} />
                  ) : (
                    <Eye size={18} />
                  )}

                </button>

              </div>

            </div>

            {/* Submit */}
            <button
              type="submit"
              className="login-button"
              disabled={loading}
            >

              {loading
                ? "Signing in..."
                : "Sign In"}

            </button>

          </form>

          <div className="login-footer">

            <ShieldText />

            <span>
              Zambia University College of Technology
            </span>

          </div>

        </div>

      </div>

    </div>
  );
}

function ShieldText() {
  return (
    <div className="login-security">
      <Lock size={13} />
    </div>
  );
}

export default Login;