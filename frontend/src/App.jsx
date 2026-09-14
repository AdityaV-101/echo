import { useEffect, useState } from "react";
import { AppProvider, useApp } from "./lib/AppContext";
import * as api from "./lib/api";
import { setMockDetected } from "./lib/mockControl";
import MockStatusBar from "./dev/MockStatusBar";
import MascotLab from "./dev/MascotLab";
import WordArtLab from "./dev/WordArtLab";
import WordArtSprite from "./assets/wordArt";
import Login from "./pages/Login";
import Home from "./pages/Home";
import WordPractice from "./pages/WordPractice";
import PracticeTracks from "./pages/PracticeTracks";
import TherapistMode from "./pages/TherapistMode";

function Router() {
  const { userId, loading, levels, levelProgress } = useApp();
  const [screen, setScreen] = useState({ name: "home" });

  if (!userId) return <Login />;
  if (loading || levels.length === 0) {
    return (
      <div className="screen screen-loading">
        <p>Loading Echo...</p>
      </div>
    );
  }

  if (screen.name === "level") {
    const level = levels.find((l) => l.level === screen.levelNumber);
    const progress = levelProgress[String(screen.levelNumber)];
    const startIndex = progress?.completed ? 0 : Math.min(progress?.words_completed ?? 0, level.words.length - 1);
    return (
      <WordPractice
        title={level.name}
        words={level.words}
        levelNumber={level.level}
        startIndex={startIndex}
        onExit={() => setScreen({ name: "home" })}
      />
    );
  }

  if (screen.name === "tracks") {
    return <PracticeTracks onExit={() => setScreen({ name: "home" })} initialPhoneme={screen.initialPhoneme} />;
  }

  if (screen.name === "therapist") {
    return <TherapistMode onExit={() => setScreen({ name: "home" })} />;
  }

  return (
    <Home
      onSelectLevel={(levelNumber) => setScreen({ name: "level", levelNumber })}
      onOpenPracticeTracks={() => setScreen({ name: "tracks", initialPhoneme: null })}
      onOpenTherapist={() => setScreen({ name: "therapist" })}
      onPracticePhoneme={(phoneme) => setScreen({ name: "tracks", initialPhoneme: phoneme })}
    />
  );
}

export default function App() {
  useEffect(() => {
    api
      .checkHealth()
      .then((h) => setMockDetected(!!h.is_mock))
      .catch(() => setMockDetected(false));
  }, []);

  if (typeof window !== "undefined" && window.location.hash === "#mascot-lab") {
    return <MascotLab />;
  }
  if (typeof window !== "undefined" && window.location.hash === "#word-art-lab") {
    return <WordArtLab />;
  }

  return (
    <AppProvider>
      <WordArtSprite />
      <MockStatusBar />
      <Router />
    </AppProvider>
  );
}
