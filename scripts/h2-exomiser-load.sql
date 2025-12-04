TRUNCATE TABLE exomiser.hp_hp_mappings;

DROP TABLE IF EXISTS exomiser.hp_hp_mappings;

CREATE TABLE exomiser.hp_hp_mappings
(
  mapping_id  INTEGER,
  hp_id       CHARACTER VARYING(10),
  hp_term     CHARACTER VARYING(200),
  hp_id_hit   CHARACTER VARYING(10),
  hp_hit_term CHARACTER VARYING(200),
  simj        DOUBLE PRECISION,
  ic          DOUBLE PRECISION,
  score       DOUBLE PRECISION,
  lcs_id      CHARACTER VARYING(20),
  lcs_term    CHARACTER VARYING(150)
);


INSERT INTO exomiser.hp_hp_mappings SELECT *
                           FROM CSVREAD('${import.path}/HP_vs_HP.txt',
                                        'mapping_id|hp_id|hp_term|hp_id_hit|hp_hit_term|simj|ic|score|lcs_id|lcs_term',
                                        'charset=UTF-8 fieldDelimiter='' fieldSeparator=| nullString=null');


CREATE INDEX hp_id1
    ON exomiser.hp_hp_mappings (hp_id);


---------------------------------------------------

TRUNCATE TABLE exomiser.hp_mp_mappings;

DROP TABLE IF EXISTS exomiser.hp_mp_mappings;

CREATE TABLE exomiser.hp_mp_mappings(
                             mapping_id INTEGER,
                             hp_id      CHARACTER VARYING(10),
                             hp_term    CHARACTER VARYING(200),
                             mp_id      CHARACTER VARYING(10),
                             mp_term    CHARACTER VARYING(200),
                             simj       DOUBLE PRECISION,
                             ic         DOUBLE PRECISION,
                             score      DOUBLE PRECISION,
                             lcs_id     CHARACTER VARYING(20),
                             lcs_term   CHARACTER VARYING(150)
);


INSERT INTO exomiser.hp_mp_mappings SELECT *
                           FROM CSVREAD('${import.path}/HP_vs_MP.txt',
                                        'mapping_id|hp_id|hp_term|mp_id|mp_term|simj|ic|score|lcs_id|lcs_term',
                                        'charset=UTF-8 fieldDelimiter='' fieldSeparator=| nullString=NULL');

CREATE INDEX hp_id2
    ON exomiser.hp_mp_mappings (hp_id);




---------------------------------------------------

TRUNCATE TABLE exomiser.hp_zp_mappings;

DROP TABLE IF EXISTS exomiser.hp_zp_mappings;

CREATE TABLE exomiser.hp_zp_mappings
(
  mapping_id INTEGER,
  hp_id      CHARACTER VARYING(10),
  hp_term    CHARACTER VARYING(200),
  zp_id      CHARACTER VARYING(10),
  zp_term    CHARACTER VARYING(200),
  simj       DOUBLE PRECISION,
  ic         DOUBLE PRECISION,
  score      DOUBLE PRECISION,
  lcs_id     CHARACTER VARYING(40),
  lcs_term   CHARACTER VARYING(150)
);


INSERT INTO exomiser.hp_zp_mappings SELECT *
                           FROM CSVREAD('${import.path}/HP_vs_ZP.txt',
                                        'mapping_id|hp_id|hp_term|zp_id|zp_term|simj|ic|score|lcs_id|lcs_term',
                                        'charset=UTF-8 fieldDelimiter='' fieldSeparator=| nullString=NULL');


CREATE INDEX hp_id3
    ON exomiser.hp_zp_mappings (hp_id);

SHUTDOWN COMPACT;
