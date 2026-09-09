"""CSV ingestion contracts, independent of the bundled music catalog."""
import csv
import pytest
from src.recommender import load_songs

FIELDS = ['id', 'title', 'artist', 'genre', 'mood', 'energy', 'tempo_bpm', 'valence', 'danceability', 'acousticness']
UNIT_FIELDS = ['energy', 'valence', 'danceability', 'acousticness']
ROW = dict(zip(FIELDS, ['1', 'A song', 'An artist', 'pop', 'happy', '.5', '120', '.5', '.5', '.5']))


def write_catalog(path, rows, fields=FIELDS):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.mark.parametrize('field', UNIT_FIELDS + ['tempo_bpm', 'id'])
@pytest.mark.parametrize('value', ['', 'not a number', 'NaN', 'inf', '-inf'])
def test_invalid_numeric_cell_rejects_entire_catalog(tmp_path, capsys, field, value):
    path = write_catalog(tmp_path / 'songs.csv', [ROW, dict(ROW, **{field: value})])
    with pytest.raises(ValueError) as error:
        load_songs(path)
    message = str(error.value)
    assert 'CSV row 3:' in message
    assert f'{field}={value!r}' in message
    assert 'expected' in message
    assert 'Loaded ' not in capsys.readouterr().out


@pytest.mark.parametrize('field', UNIT_FIELDS)
@pytest.mark.parametrize('value', ['-0.001', '1.001'])
def test_unit_features_reject_values_outside_inclusive_range(tmp_path, field, value):
    path = write_catalog(tmp_path / 'songs.csv', [dict(ROW, **{field: value})])
    with pytest.raises(ValueError, match='between 0 and 1'):
        load_songs(path)


@pytest.mark.parametrize('value', ['0', '-1'])
def test_tempo_must_be_positive(tmp_path, value):
    path = write_catalog(tmp_path / 'songs.csv', [dict(ROW, tempo_bpm=value)])
    with pytest.raises(ValueError, match='tempo_bpm=.*greater than 0'):
        load_songs(path)


def test_id_requires_integer(tmp_path):
    path = write_catalog(tmp_path / 'songs.csv', [dict(ROW, id='1.5')])
    with pytest.raises(ValueError, match='id=.*expected an integer'):
        load_songs(path)


@pytest.mark.parametrize('field', UNIT_FIELDS + ['tempo_bpm', 'id'])
def test_missing_numeric_header_is_reported_even_without_records(tmp_path, field):
    path = write_catalog(tmp_path / 'songs.csv', [], [f for f in FIELDS if f != field])
    with pytest.raises(ValueError) as error:
        load_songs(path)
    assert 'CSV row 1:' in str(error.value) and field in str(error.value)


def test_short_record_identifies_missing_numeric_cell(tmp_path):
    path = tmp_path / 'songs.csv'
    path.write_text(','.join(FIELDS) + '\n' + ','.join(ROW[f] for f in FIELDS[:-1]) + '\n')
    with pytest.raises(ValueError, match='CSV row 2: acousticness=None; expected'):
        load_songs(path)


def test_valid_boundaries_and_quoted_text_are_preserved(tmp_path):
    rows = [dict(ROW, id=str(i+1), title='A "quoted", song\nsecond line',
                 **{f: str(boundary) for f in UNIT_FIELDS}, tempo_bpm='0.01')
            for i, boundary in enumerate([0, 1])]
    songs = load_songs(write_catalog(tmp_path / 'songs.csv', rows))
    assert len(songs) == 2
    for song, row in zip(songs, rows):
        assert song.title == row['title']
        assert song.id == int(row['id'])
        for field in UNIT_FIELDS + ['tempo_bpm']:
            assert getattr(song, field) == float(row[field])


def test_error_row_counts_records_when_titles_contain_newlines(tmp_path):
    path = write_catalog(tmp_path / 'songs.csv', [dict(ROW, title='Two\nlines'), dict(ROW, energy='2')])
    with pytest.raises(ValueError, match='CSV row 3: energy='):
        load_songs(path)


def test_header_only_catalog_is_empty(tmp_path):
    assert load_songs(write_catalog(tmp_path / 'songs.csv', [])) == []


def test_missing_file_retains_file_not_found_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_songs(tmp_path / 'missing.csv')
