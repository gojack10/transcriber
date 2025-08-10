--
-- PostgreSQL database dump
--

-- Dumped from database version 15.13 (Debian 15.13-1.pgdg120+1)
-- Dumped by pg_dump version 15.13 (Debian 15.13-1.pgdg120+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: gojack10
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO gojack10;

--
-- Name: downloaded_videos; Type: TABLE; Schema: public; Owner: gojack10
--

CREATE TABLE public.downloaded_videos (
    id integer NOT NULL,
    url character varying,
    status character varying NOT NULL,
    download_date timestamp without time zone NOT NULL,
    local_path character varying,
    yt_dlp_processed boolean DEFAULT false
);


ALTER TABLE public.downloaded_videos OWNER TO gojack10;

--
-- Name: downloaded_videos_id_seq; Type: SEQUENCE; Schema: public; Owner: gojack10
--

CREATE SEQUENCE public.downloaded_videos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.downloaded_videos_id_seq OWNER TO gojack10;

--
-- Name: downloaded_videos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: gojack10
--

ALTER SEQUENCE public.downloaded_videos_id_seq OWNED BY public.downloaded_videos.id;


--
-- Name: transcribed; Type: TABLE; Schema: public; Owner: gojack10
--

CREATE TABLE public.transcribed (
    id integer NOT NULL,
    utc_time timestamp with time zone NOT NULL,
    url character varying,
    video_title character varying NOT NULL,
    content text NOT NULL,
    pst_time character varying
);


ALTER TABLE public.transcribed OWNER TO gojack10;

--
-- Name: transcribed_id_seq; Type: SEQUENCE; Schema: public; Owner: gojack10
--

CREATE SEQUENCE public.transcribed_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.transcribed_id_seq OWNER TO gojack10;

--
-- Name: transcribed_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: gojack10
--

ALTER SEQUENCE public.transcribed_id_seq OWNED BY public.transcribed.id;


--
-- Name: downloaded_videos id; Type: DEFAULT; Schema: public; Owner: gojack10
--

ALTER TABLE ONLY public.downloaded_videos ALTER COLUMN id SET DEFAULT nextval('public.downloaded_videos_id_seq'::regclass);


--
-- Name: transcribed id; Type: DEFAULT; Schema: public; Owner: gojack10
--

ALTER TABLE ONLY public.transcribed ALTER COLUMN id SET DEFAULT nextval('public.transcribed_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: gojack10
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: downloaded_videos downloaded_videos_pkey; Type: CONSTRAINT; Schema: public; Owner: gojack10
--

ALTER TABLE ONLY public.downloaded_videos
    ADD CONSTRAINT downloaded_videos_pkey PRIMARY KEY (id);


--
-- Name: transcribed transcribed_pkey; Type: CONSTRAINT; Schema: public; Owner: gojack10
--

ALTER TABLE ONLY public.transcribed
    ADD CONSTRAINT transcribed_pkey PRIMARY KEY (id);


--
-- Name: ix_downloaded_videos_id; Type: INDEX; Schema: public; Owner: gojack10
--

CREATE INDEX ix_downloaded_videos_id ON public.downloaded_videos USING btree (id);


--
-- Name: ix_downloaded_videos_url; Type: INDEX; Schema: public; Owner: gojack10
--

CREATE UNIQUE INDEX ix_downloaded_videos_url ON public.downloaded_videos USING btree (url);


--
-- Name: ix_transcribed_id; Type: INDEX; Schema: public; Owner: gojack10
--

CREATE INDEX ix_transcribed_id ON public.transcribed USING btree (id);


--
-- Name: ix_transcribed_url; Type: INDEX; Schema: public; Owner: gojack10
--

CREATE UNIQUE INDEX ix_transcribed_url ON public.transcribed USING btree (url);


--
-- PostgreSQL database dump complete
--

