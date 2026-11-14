// Run locally (never against production):
// npm install --no-save firebase @firebase/rules-unit-testing
// firebase emulators:exec --only firestore --project demo-ipod-friends-test "node tests/friends.rules.cjs"
'use strict';
const fs=require('node:fs'),path=require('node:path');
const {initializeTestEnvironment,assertFails,assertSucceeds}=require('@firebase/rules-unit-testing');
const {doc,collection,query,where,getDocs,getDoc,setDoc,updateDoc,writeBatch,serverTimestamp}=require('firebase/firestore');
(async()=>{
 const env=await initializeTestEnvironment({
   projectId:'demo-ipod-friends-test',
   firestore:{rules:fs.readFileSync(path.resolve(__dirname,'../firestore.rules'),'utf8')}
 });
 const a=env.authenticatedContext('alice').firestore();
 const b=env.authenticatedContext('bob').firestore();
 const c=env.authenticatedContext('charlie').firestore();
 const anon=env.unauthenticatedContext().firestore();
 const create=async(db,id,username)=>{
   const batch=writeBatch(db);
   batch.set(doc(db,'profiles',id),{uid:id,username,displayName:username,sharing:false,
     createdAt:serverTimestamp(),updatedAt:serverTimestamp()});
   batch.set(doc(db,'handles',username),{uid:id});
   await assertSucceeds(batch.commit());
 };
 try{
   await create(a,'alice','alice_1');
   await create(b,'bob','bob_1');
   await assertFails(getDoc(doc(anon,'profiles','alice')));
   await assertFails(getDocs(collection(a,'profiles')));
   await assertFails(getDocs(collection(a,'handles')));
   await assertFails(setDoc(doc(c,'profiles','charlie'),{uid:'charlie',username:'charlie_1',displayName:'Charlie',sharing:false,
     createdAt:serverTimestamp(),updatedAt:serverTimestamp()}));
   await assertFails(updateDoc(doc(a,'profiles','bob'),{displayName:'Hacked',updatedAt:serverTimestamp()}));
   await assertFails(setDoc(doc(c,'handles','alice_1'),{uid:'charlie'}));
   // Looking at someone's card checks both request ids before any request exists.
   await assertSucceeds(getDoc(doc(a,'friendRequests','alice_bob')));
   await assertSucceeds(getDoc(doc(a,'friendRequests','bob_alice')));
   await assertFails(getDoc(doc(c,'friendRequests','alice_bob')));
   const req=doc(a,'friendRequests','alice_bob');
   await assertSucceeds(setDoc(req,{from:'alice',to:'bob',status:'pending',
     createdAt:serverTimestamp(),updatedAt:serverTimestamp()}));
   await assertFails(updateDoc(req,{status:'accepted',updatedAt:serverTimestamp()}));
   await assertSucceeds(getDocs(query(collection(b,'friendRequests'),where('to','==','bob'))));
   await assertSucceeds(updateDoc(doc(b,'friendRequests','alice_bob'),{status:'accepted',updatedAt:serverTimestamp()}));
   const recent=[{title:'Yellow',artist:'Coldplay',album:'Parachutes',artworkUrl:'',listenedAt:new Date()}];
   await assertSucceeds(setDoc(doc(a,'activity','alice'),{uid:'alice',recent,updatedAt:serverTimestamp()}));
   await assertFails(getDoc(doc(b,'activity','alice'))); // sharing is OFF
   await assertSucceeds(updateDoc(doc(a,'profiles','alice'),{sharing:true,updatedAt:serverTimestamp()}));
   await assertSucceeds(getDoc(doc(b,'activity','alice')));
   await assertFails(getDoc(doc(c,'activity','alice')));
   await assertSucceeds(updateDoc(doc(a,'profiles','alice'),{sharing:false,updatedAt:serverTimestamp()}));
   await assertFails(getDoc(doc(b,'activity','alice')));
   console.log('PASS Firestore ownership, username uniqueness, friend approval, privacy and activity rules');
 }finally{await env.cleanup()}
})().catch(e=>{console.error(e);process.exitCode=1});
