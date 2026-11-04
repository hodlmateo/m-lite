CREATE TABLE notes (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT ''
);

INSERT INTO notes (id, title, body, tags) VALUES
  (
    'pantry-salt',
    'Pantry salt',
    'The fictional pantry keeps flake salt in a blue tin on the second shelf. The tin has no label.',
    'pantry'
  ),
  (
    'pip-symbol',
    'PIP symbol',
    'PIP is a made-up paper symbol. Rows in the price file are synthetic and do not quote a market.',
    'desk'
  );
