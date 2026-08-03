-- Backfill highest_difficulty for legacy rows
UPDATE public.player_scoreboard
SET highest_difficulty = CASE
    WHEN nightmare_wins + nightmare_losses + nightmare_draws > 0 THEN 'Nightmare'
    WHEN hard_wins + hard_losses + hard_draws > 0 THEN 'Hard'
    WHEN normal_wins + normal_losses + normal_draws + medium_wins + medium_losses + medium_draws > 0 THEN 'Normal'
    ELSE 'Easy'
END
WHERE highest_difficulty IS NULL OR highest_difficulty = 'Easy';
