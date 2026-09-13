import { useState } from "react";
import { AppProvider, useApp } from "./lib/AppContext";
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
  return (
    <AppProvider>
      <Router />
    </AppProvider>
  );
}
