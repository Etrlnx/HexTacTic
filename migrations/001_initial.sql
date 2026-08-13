-- Initial player scoreboard schema
CREATE TABLE IF NOT EXISTS public.player_scoreboard (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    easy_wins INT NOT NULL DEFAULT 0,
    easy_losses INT NOT NULL DEFAULT 0,
    easy_draws INT NOT NULL DEFAULT 0,
    normal_wins INT NOT NULL DEFAULT 0,
    normal_losses INT NOT NULL DEFAULT 0,
    normal_draws INT NOT NULL DEFAULT 0,
    medium_wins INT NOT NULL DEFAULT 0,
    medium_losses INT NOT NULL DEFAULT 0,
    medium_draws INT NOT NULL DEFAULT 0,
    hard_wins INT NOT NULL DEFAULT 0,
    hard_losses INT NOT NULL DEFAULT 0,
    hard_draws INT NOT NULL DEFAULT 0,
    nightmare_wins INT NOT NULL DEFAULT 0,
    nightmare_losses INT NOT NULL DEFAULT 0,
    nightmare_draws INT NOT NULL DEFAULT 0,
    highest_difficulty TEXT NOT NULL DEFAULT 'Easy',
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
