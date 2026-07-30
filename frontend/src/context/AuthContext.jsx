import { createContext, useEffect, useState } from "react";
import {
  deleteProfile,
  getProfile,
  loginUser,
  logoutUser,
  registerUser,
  updateProfile
} from "../api/auth";
import { clearSession, readSession, saveSession } from "../services/storage";

export const AuthContext = createContext({
  user: null,
  authLoading: true,
  signInLoading: false,
  signUpLoading: false,
  profileSaving: false,
  signIn: async () => {},
  signUp: async () => {},
  signOut: async () => {},
  refreshProfile: async () => {},
  saveProfile: async () => {},
  removeProfile: async () => {}
});

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [signInLoading, setSignInLoading] = useState(false);
  const [signUpLoading, setSignUpLoading] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);

  useEffect(() => {
    const data = readSession();
    if (data?.user) {
      setUser(data.user);
    }
    setAuthLoading(false);
  }, []);

  const persistUser = (nextUser) => {
    const currentSession = readSession();
    if (currentSession) {
      const nextSession = { ...currentSession, user: nextUser };
      saveSession(nextSession);
    }
    setUser(nextUser);
  };

  const signIn = async (credentials) => {
    setSignInLoading(true);

    try {
      const session = await loginUser(credentials);
      saveSession(session);
      setUser(session.user);
      return session;
    } finally {
      setSignInLoading(false);
    }
  };

  const signOut = async () => {
    await logoutUser();
    clearSession();
    setUser(null);
  };

  const signUp = async (payload) => {
    setSignUpLoading(true);

    try {
      const session = await registerUser(payload);
      saveSession(session);
      setUser(session.user);
      return session;
    } finally {
      setSignUpLoading(false);
    }
  };

  const refreshProfile = async () => {
    const profile = await getProfile();
    persistUser(profile);
    return profile;
  };

  const saveProfile = async (payload) => {
    setProfileSaving(true);
    try {
      const profile = await updateProfile(payload);
      persistUser(profile);
      return profile;
    } finally {
      setProfileSaving(false);
    }
  };

  const removeProfile = async () => {
    setProfileSaving(true);
    try {
      await deleteProfile();
      clearSession();
      setUser(null);
    } finally {
      setProfileSaving(false);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        authLoading,
        signInLoading,
        signUpLoading,
        profileSaving,
        signIn,
        signUp,
        signOut,
        refreshProfile,
        saveProfile,
        removeProfile
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
