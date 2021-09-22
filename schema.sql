--
-- PostgreSQL database dump
--

-- Dumped from database version 10.7 (Ubuntu 10.7-0ubuntu0.18.04.1)
-- Dumped by pg_dump version 10.7 (Ubuntu 10.7-0ubuntu0.18.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: plpgsql; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS plpgsql WITH SCHEMA pg_catalog;


--
-- Name: EXTENSION plpgsql; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION plpgsql IS 'PL/pgSQL procedural language';


SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: guilds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.guilds (
    id bigint,
    name text,
    surrenderat20notifchannel bigint,
    twitchnotifchannel bigint,
    youtubenotifchannel bigint,
    redditnotifchannel bigint
);


--
-- Name: keywords; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.keywords (
    keyword text,
    guild bigint
);


--
-- Name: subreddits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subreddits (
    id text,
    name text,
    lastpostid text,
    lastposttime numeric
);


--
-- Name: subredditsubscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subredditsubscriptions (
    subreddit text,
    guild bigint
);


--
-- Name: surrenderat20subscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.surrenderat20subscriptions (
    guild bigint,
    redposts boolean,
    pbe boolean,
    rotations boolean,
    esports boolean,
    releases boolean,
    other boolean DEFAULT true,
    lastpostid character varying,
    lastupdated integer,
    updates integer,
    lastpostmessage bigint
);


--
-- Name: twitchchannels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.twitchchannels (
    id text,
    name text,
    lastlive timestamp with time zone
);


--
-- Name: twitchsubscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.twitchsubscriptions (
    twitchchannel text,
    guild bigint
);


--
-- Name: youtubechannels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.youtubechannels (
    id text,
    name text,
    lastlive timestamp with time zone,
    lastvideoid text,
    videocount bigint
);


--
-- Name: youtubesubscriptions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.youtubesubscriptions (
    youtubechannel text,
    guild bigint,
    onlystreams boolean
);


--
-- PostgreSQL database dump complete
--

